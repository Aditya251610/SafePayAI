"""Settings for checkout. Env prefix PS_CHECKOUT_ per
docs/service-skeleton-conventions.md section 2. Names from
.claude/prd/services/checkout/{spec.md section 14, deployment.md section 3}.

INTERNAL_TICK_SECRET is the one deliberately unprefixed exception documented for this
service (shared cron-trigger name across services with an /internal/tick-style endpoint).
Forbidden here (CI env-manifest test, deployment.md section 3): PAYPAL_CLIENT_ID,
PAYPAL_CLIENT_SECRET, LLM_API_KEY, MANDATE_HMAC_KEY, APPROVAL_KEY.
"""

from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from safepayai_common.outbox import DEV_AUDIT_RELAY_KID, DEV_AUDIT_RELAY_PRIVATE_KEY_PEM
from safepayai_common.startup_guard import assert_no_placeholder_secrets


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PS_CHECKOUT_",
        env_file=".env",
        extra="ignore",
    )

    service_name: str = "checkout"
    log_level: str = "info"
    currency: str = "USD"

    # Explicit alias: CLAUDE.md's documented convention is PS_<SLUG>_{DATABASE_URL,
    # MIGRATION_DATABASE_URL} (every other service and ci-python-service.yml use this) --
    # without it, CI's exported env vars are never read and migrations silently fall back
    # to these dev defaults, failing auth against CI's postgres container as "mig_checkout".
    db_url: str = Field(
        default="postgresql+asyncpg://svc_checkout:changeme@localhost:5432/artiq",
        alias="PS_CHECKOUT_DATABASE_URL",
    )
    migration_db_url: str = Field(
        default="postgresql+asyncpg://mig_checkout:changeme@localhost:5432/artiq",
        alias="PS_CHECKOUT_MIGRATION_DATABASE_URL",
    )
    db_pool_size: int = 2

    internal_jwks_url: str = "http://localhost:8080/.well-known/jwks.json"
    internal_jwt_audience: str = "checkout"
    service_signing_key: str | None = None
    service_signing_kid: str | None = None

    catalog_base_url: str = "http://localhost:8000"
    mandate_base_url: str = "http://localhost:8000"
    shopping_agent_base_url: str = "http://localhost:8000"
    paypal_adapter_base_url: str = "http://localhost:8000"
    audit_base_url: str = "http://localhost:8000"

    ticket_hmac_key: str | None = None
    ticket_hmac_kid: str = "k1"
    ticket_ttl_seconds: int = 120
    return_base_url: str = "http://localhost:3000"
    return_state_ttl_seconds: int = 1800
    order_approval_ttl_seconds: int = 3600

    http_timeout_catalog_ms: int = 2000
    http_timeout_mandate_ms: int = 2000
    http_timeout_intent_fit_ms: int = 4000
    http_timeout_adapter_ms: int = 5000

    reconcile_grace_seconds: int = 60
    pending_poll_max_attempts: int = 5
    outbox_flush_interval_seconds: int = 30

    # Outbox relay (S2-06): see mandate/app/settings.py for the full rationale comment.
    outbox_relay_audit_base_url: str = "http://localhost:8000"
    outbox_relay_jwt_kid: str = DEV_AUDIT_RELAY_KID
    outbox_relay_jwt_issuer: str = "ps-checkout"
    outbox_relay_jwt_private_key: str = DEV_AUDIT_RELAY_PRIVATE_KEY_PEM
    outbox_relay_batch_size: int = 100

    inprocess_transport: bool = False

    # Deliberately unprefixed per conventions doc section 2 (shared cron-trigger name).
    internal_tick_secret: str | None = Field(default=None, alias="INTERNAL_TICK_SECRET")

    @model_validator(mode="after")
    def _no_placeholder_secrets(self) -> Settings:
        assert_no_placeholder_secrets(
            {
                "PS_CHECKOUT_TICKET_HMAC_KEY": self.ticket_hmac_key,
                "INTERNAL_TICK_SECRET": self.internal_tick_secret,
            }
        )
        return self


def get_settings() -> Settings:
    return Settings()
