"""Settings for tracking.

Env prefix PS_TRACKING_ per docs/service-skeleton-conventions.md section 2.

Bug fix (Wave 5B, CLAUDE.md "known recurring failure classes" - CI integration env vars):
tracking/spec.md section 9 names the DB url `PS_TRACKING_DB_URL`, but CLAUDE.md's
platform-wide hard rule and ci-python-service.yml's exported env vars use
PS_<SLUG>_{DATABASE_URL,MIGRATION_DATABASE_URL} for every service; this exact mismatch was
independently found and fixed in 3 other services' settings.py this session. Using the
spec's name here would make CI silently fall back to the dev default and fail auth as
mig_tracking against CI's postgres container. Flagged for the tracking spec.md owner to
update section 9 to match the platform convention.
INTERNAL_TICK_SECRET remains the one documented bare-name exception (shared cron-trigger
name across every service with an /internal/tick-style endpoint).
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from safepayai_common.outbox import DEV_AUDIT_RELAY_KID, DEV_AUDIT_RELAY_PRIVATE_KEY_PEM


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PS_TRACKING_", extra="ignore")

    service_name: str = "tracking"

    # Database (CLAUDE.md platform convention: PS_<SLUG>_{DATABASE_URL,MIGRATION_DATABASE_URL})
    db_url: str = Field(
        default="postgresql+asyncpg://svc_tracking:changeme@localhost:5432/artiq",
        alias="PS_TRACKING_DATABASE_URL",
    )
    migration_db_url: str = Field(
        default="postgresql+asyncpg://mig_tracking:changeme@localhost:5432/artiq",
        alias="PS_TRACKING_MIGRATION_DATABASE_URL",
    )

    # Sandbox / demo controls
    sandbox_mode: bool = False
    demo_controls_enabled: bool = False
    demo_max_advance_seconds: int = 2592000
    demo_max_actions_per_minute: int = 30

    # Late/lost thresholds (config, values TBD per spec.md C8)
    late_grace_seconds: int = 86400
    lost_after_seconds: int = 604800
    lost_after_promise_seconds: int = 1209600

    # Ticking / polling
    tick_interval_seconds: int = 30
    tick_lease_seconds: int = 20
    tick_enable_inprocess: bool = True

    # Outbox
    outbox_max_attempts: int = 10
    outbox_backoff_base_seconds: int = 5

    # Outbox relay (S2-06): see mandate/app/settings.py for the full rationale comment.
    outbox_relay_audit_base_url: str = "http://localhost:8000"
    outbox_relay_jwt_kid: str = DEV_AUDIT_RELAY_KID
    outbox_relay_jwt_issuer: str = "ps-tracking"
    outbox_relay_jwt_private_key: str = DEV_AUDIT_RELAY_PRIVATE_KEY_PEM
    outbox_relay_batch_size: int = 100

    # Auth (internal service-JWT verification, see deps.py)
    internal_jwks_url: str = ""
    internal_audience: str = "tracking"

    # Outbound service-JWT self-minting (tracking -> checkout/paypal-adapter/resolution/audit).
    service_signing_key: str = ""
    service_signing_kid: str = ""

    # Event push HMAC (outbound outbox delivery signing)
    event_push_hmac_key: str = ""

    # Downstream base URLs (http or inproc:)
    paypal_adapter_url: str = ""
    checkout_url: str = ""
    audit_url: str = ""
    resolution_url: str = ""

    # Transport mode (Profile A http vs Profile B inproc)
    service_transport: str = "http"

    log_level: str = "INFO"

    # Bare-name exception (shared cron-trigger secret; see conventions doc section 2)
    internal_tick_secret: str = Field(default="", alias="INTERNAL_TICK_SECRET")


settings = Settings()
