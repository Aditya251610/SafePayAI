"""Settings for paypal-adapter. Env prefix PS_PAYPALADAPTER_ per
docs/service-skeleton-conventions.md section 2. Names from
.claude/prd/services/paypal-adapter/spec.md section 12 / deployment.md section 2.

PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET are the one documented bare-name exception for this
service (spec.md section 12: kept as-is rather than renamed, matches the already-tested
sandbox spike and .env). PS_CHECKOUT_TICKET_HMAC_KEY / PS_RESOLUTION_TICKET_HMAC_KEY are
named after the minting services (checkout, resolution) and consumed here for ticket
verification -- this service holds both, each minter holds only its own.

Forbidden in this env (CI manifest test): LLM_API_KEY, session/CSRF/mandate/approval keys.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PS_PAYPALADAPTER_",
        env_file=".env",
        extra="ignore",
    )

    service_name: str = "paypal-adapter"
    log_level: str = "info"
    trace_header: str = "X-Trace-Id"

    # Deliberately unprefixed exception (spec.md section 12).
    paypal_client_id: str | None = Field(default=None, alias="PAYPAL_CLIENT_ID")
    paypal_client_secret: str | None = Field(default=None, alias="PAYPAL_CLIENT_SECRET")

    paypal_mode: str = "sandbox"
    paypal_base_url: str = "https://api-m.sandbox.paypal.com"
    paypal_timeout_seconds: float = 10.0
    paypal_max_concurrency: int = 4
    paypal_get_retries: int = 2
    paypal_token_refresh_skew_seconds: int = 60
    paypal_return_url_allowed_origins: str = "http://localhost:3000"

    # Explicit alias: CLAUDE.md's documented convention is PS_<SLUG>_{DATABASE_URL,
    # MIGRATION_DATABASE_URL} (every other service and ci-python-service.yml use this) --
    # the DB_URL/MIGRATION_DB_URL names previously here were never read by CI's exported
    # env vars, silently falling back to these dev defaults and failing against CI's
    # postgres container as role "mig_paypal" with the wrong password/database.
    db_url: str = Field(
        default="postgresql+asyncpg://svc_paypal:changeme@localhost:5432/artiq",
        alias="PS_PAYPALADAPTER_DATABASE_URL",
    )
    migration_db_url: str = Field(
        default="postgresql+asyncpg://mig_paypal:changeme@localhost:5432/artiq",
        alias="PS_PAYPALADAPTER_MIGRATION_DATABASE_URL",
    )

    internal_jwks_url: str | None = None
    internal_trusted_issuers: str | None = None
    internal_jwt_aud: str = "paypal-adapter"

    # Ticket verification keys, named after the minting service (spec.md section 5.4/12).
    checkout_ticket_hmac_key: str | None = Field(default=None, alias="PS_CHECKOUT_TICKET_HMAC_KEY")
    resolution_ticket_hmac_key: str | None = Field(
        default=None, alias="PS_RESOLUTION_TICKET_HMAC_KEY"
    )
    checkout_ticket_hmac_kid: str | None = Field(default=None, alias="PS_CHECKOUT_TICKET_HMAC_KID")
    resolution_ticket_hmac_kid: str | None = Field(
        default=None, alias="PS_RESOLUTION_TICKET_HMAC_KID"
    )

    ticket_ttl_seconds: int = 120
    ticket_skew_seconds: int = 10

    money_enabled: bool = False  # unset/unparseable = frozen, fail closed (spec.md section 9)
    refund_max_minor: int = 50000

    caller_allowlist_json: str | None = None

    rate_limit_read_per_min: int = 120
    rate_limit_money_per_min: int = 30

    audit_push_url: str = "http://localhost:8000"
    outbox_flush_secret: str | None = None

    webhook_enabled: bool = False
    paypal_webhook_id: str | None = None

    demo_inspector_enabled: bool = False


def get_settings() -> Settings:
    return Settings()
