"""Settings for resolution (Wave 4 skeleton).

Env prefix PS_RESOLUTION_ per docs/service-skeleton-conventions.md section 2. Names copied
verbatim from services/resolution/{spec.md section 14, deployment.md section 3}.
REFUNDS_FROZEN is NOT an env var (deployment.md section 7: it is a DB row, resolution's own
global kill switch) — PS_RESOLUTION_REFUNDS_FROZEN_DEFAULT only seeds the first row.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from safepayai_common.outbox import DEV_AUDIT_RELAY_KID, DEV_AUDIT_RELAY_PRIVATE_KEY_PEM


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PS_RESOLUTION_", extra="ignore")

    service_id: str = "resolution"

    # CLAUDE.md platform convention: PS_<SLUG>_{DATABASE_URL,MIGRATION_DATABASE_URL}.
    # database_url derives its env var from env_prefix + field name (PS_RESOLUTION_DATABASE_URL)
    # automatically; migration_database_url needs an explicit default so migrations/env.py has
    # somewhere to fall back to when the migration-role URL isn't set (mirrors mandate/checkout).
    database_url: str = Field(
        default="postgresql+asyncpg://svc_resolution:changeme@localhost:5432/artiq",
    )
    migration_database_url: str = Field(
        default="postgresql+asyncpg://mig_resolution:changeme@localhost:5432/artiq",
    )
    db_pool_size: int = 2
    transport: str = "http"

    internal_jwt_signing_key: str = ""
    internal_jwt_kid: str = ""
    internal_jwt_trusted_issuers: str = "api-gateway"
    internal_jwks_url: str = ""

    ticket_hmac_key: str = ""
    ticket_hmac_kid: str = "k1"
    ticket_ttl_seconds: int = 120

    mandate_url: str = ""
    checkout_url: str = ""
    tracking_url: str = ""
    triage_ai_url: str = ""
    paypal_adapter_url: str = ""
    audit_url: str = ""

    approval_link_hmac_key: str = ""
    approval_link_ttl_s: int = 86400
    approval_base_url: str = ""

    policy_version: str = "v1"
    policy_refund_cap_minor: int = 5000
    policy_excluded_categories: str = ""
    policy_velocity_max: int = 2
    policy_velocity_window_days: int = 30

    triage_min_confidence: float = 0.7
    triage_timeout_s: float = 4.0
    adapter_timeout_s: float = 10.0

    preauth_auto_execute: bool = False

    # Seeds the control_flags row ONLY; cannot unfreeze an existing row (deployment.md section 7).
    refunds_frozen_default: bool = True

    flag_cache_ttl_s: int = 5

    reconcile_interval_s: int = 300
    refund_min_reconcile_age_s: int = 60
    reconcile_max_attempts: int = 10

    outbox_relay_interval_s: int = 15

    # Outbox relay (S2-06): see mandate/app/settings.py for the full rationale comment.
    outbox_relay_audit_base_url: str = "http://localhost:8000"
    outbox_relay_jwt_kid: str = DEV_AUDIT_RELAY_KID
    outbox_relay_jwt_issuer: str = "ps-resolution"
    outbox_relay_jwt_private_key: str = DEV_AUDIT_RELAY_PRIVATE_KEY_PEM
    outbox_relay_batch_size: int = 100

    human_review_sla_target_s: int | None = None
    case_report_max_chars: int = 4000

    # POST /internal/tick window checks (T12/T21/T22/T23) -- no spec-given numbers, so these
    # are small documented defaults rather than magic numbers inline in the tick use case.
    resolution_grace_period_s: int = (
        3600  # RESOLVED_REFUNDED/RESOLVED_RESHIP -> CLOSED (I)
    )
    appeal_window_s: int = 259200  # DECLINED -> CLOSED, 3 days (I)
    tick_reconcile_limit: int = (
        50  # reconcile_attempts() limit when driven by the tick, not a request
    )

    tick_secret: str = ""
    demo_mode: bool = True
    log_level: str = "INFO"


settings = Settings()
