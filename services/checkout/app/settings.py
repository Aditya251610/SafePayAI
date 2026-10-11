"""Settings for checkout. Env prefix PS_CHECKOUT_ per
docs/service-skeleton-conventions.md section 2. Names from
.claude/prd/services/checkout/{spec.md section 14, deployment.md section 3}.

INTERNAL_TICK_SECRET is the one deliberately unprefixed exception documented for this
service (shared cron-trigger name across services with an /internal/tick-style endpoint).
Forbidden here (CI env-manifest test, deployment.md section 3): PAYPAL_CLIENT_ID,
PAYPAL_CLIENT_SECRET, LLM_API_KEY, MANDATE_HMAC_KEY, APPROVAL_KEY.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PS_CHECKOUT_",
        env_file=".env",
        extra="ignore",
    )

    service_name: str = "checkout"
    log_level: str = "info"
    currency: str = "USD"

    db_url: str = "postgresql+asyncpg://svc_checkout:changeme@localhost:5432/artiq"
    # Not explicitly listed in deployment.md's env table (only PS_CHECKOUT_DATABASE_URL is);
    # added for Alembic's direct connection per data-architecture.md section 8. Flagged.
    migration_db_url: str = "postgresql+asyncpg://mig_checkout:changeme@localhost:5432/artiq"
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

    inprocess_transport: bool = False

    # Deliberately unprefixed per conventions doc section 2 (shared cron-trigger name).
    internal_tick_secret: str | None = Field(default=None, alias="INTERNAL_TICK_SECRET")


def get_settings() -> Settings:
    return Settings()
