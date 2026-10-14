"""Pydantic-settings configuration for mandate.

Env prefix PS_MANDATE_ per docs/service-skeleton-conventions.md section 2. The
`MANDATE_HMAC_KEY` / `MANDATE_HMAC_KEY_PREVIOUS` secrets stay bare (no prefix) -
this is one of the three documented exceptions (conventions doc section 2), settled
in .claude/prd/services/mandate/spec.md section 12 C5. `INTERNAL_TICK_SECRET` is
the shared cron-trigger name used by /internal/* endpoints.
"""

from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from safepayai_common.outbox import DEV_AUDIT_RELAY_KID, DEV_AUDIT_RELAY_PRIVATE_KEY_PEM
from safepayai_common.startup_guard import assert_no_placeholder_secrets


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PS_MANDATE_", extra="ignore")

    app_env: str = "local"
    log_level: str = "INFO"
    port: int = 8000

    database_url: str = "postgresql+asyncpg://svc_mandate:password@localhost:5432/artiq"
    db_pool_size: int = 2
    migration_database_url: str = (
        "postgresql+asyncpg://mig_mandate:password@localhost:5432/artiq"
    )

    hmac_key_id: str = "k1"
    hmac_key_id_previous: str | None = None

    internal_jwt_audience: str = "mandate"
    trusted_issuers: str | None = None
    internal_jwks_url: str | None = None

    policy_version: str = "policy.v1"
    currency: str = "USD"

    max_total_ceiling_minor: int = 100_000
    default_max_qty_per_line: int = 5
    max_qty_per_line_ceiling: int = 20
    max_merchants: int = 5
    intent_max_chars: int = 500

    min_expiry_seconds: int = 3600
    max_expiry_seconds: int = 60 * 60 * 24 * 30

    refund_cap_ceiling_minor: int = 50_000
    deliver_by_days_min: int = 1
    deliver_by_days_max: int = 30

    nonce_ttl_seconds: int = 120
    idempotency_ttl_seconds: int = 60 * 60 * 24

    reservation_ttl_seconds: int = 900
    stuck_capture_alert_seconds: int = 600
    exhaust_dust_minor: int = 0

    lock_timeout_ms: int = 3000
    statement_timeout_ms: int = 10_000

    advisory_near_cap_percent: int = 90
    advisory_expires_soon_seconds: int = 3600

    signing_enabled: bool = True

    audit_base_url: str | None = None
    checkout_base_url: str | None = None
    resolution_base_url: str | None = None
    inprocess_transport: bool = False
    outbox_flush_interval_seconds: int = 30

    # Outbox relay (S2-06): self-issued service JWT for pushing this service's own
    # outbox rows to audit's /internal/events/batch. Dev defaults come from
    # safepayai_common.outbox's non-secret fixture keypair (mirrors services/audit's
    # own local_jwks.json pattern) so docker-compose/CI work without extra setup; a real
    # deployment overrides the private key and updates audit's PS_AUDIT_TRUSTED_ISSUERS.
    outbox_relay_audit_base_url: str = "http://localhost:8000"
    outbox_relay_jwt_kid: str = DEV_AUDIT_RELAY_KID
    outbox_relay_jwt_issuer: str = "ps-mandate"
    outbox_relay_jwt_private_key: str = DEV_AUDIT_RELAY_PRIVATE_KEY_PEM
    outbox_relay_batch_size: int = 100


class BareSecrets(BaseSettings):
    """The settled unprefixed exceptions (spec.md section 12 C5 / section 13)."""

    model_config = SettingsConfigDict(extra="ignore")

    mandate_hmac_key: str | None = None
    mandate_hmac_key_previous: str | None = None
    internal_tick_secret: str | None = None

    @model_validator(mode="after")
    def _no_placeholder_secrets(self) -> BareSecrets:
        assert_no_placeholder_secrets(
            {
                "MANDATE_HMAC_KEY": self.mandate_hmac_key,
                "MANDATE_HMAC_KEY_PREVIOUS": self.mandate_hmac_key_previous,
                "INTERNAL_TICK_SECRET": self.internal_tick_secret,
            }
        )
        return self


def get_settings() -> Settings:
    return Settings()


def get_bare_secrets() -> BareSecrets:
    return BareSecrets()
