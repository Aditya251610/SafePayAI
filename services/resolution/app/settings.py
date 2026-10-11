"""Settings for resolution (Wave 4 skeleton).

Env prefix PS_RESOLUTION_ per docs/service-skeleton-conventions.md section 2. Names copied
verbatim from services/resolution/{spec.md section 14, deployment.md section 3}.
REFUNDS_FROZEN is NOT an env var (deployment.md section 7: it is a DB row, resolution's own
global kill switch) — PS_RESOLUTION_REFUNDS_FROZEN_DEFAULT only seeds the first row.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PS_RESOLUTION_", extra="ignore")

    service_id: str = "resolution"

    database_url: str = ""
    db_pool_size: int = 2
    transport: str = "http"

    internal_jwt_signing_key: str = ""
    internal_jwt_kid: str = ""
    internal_jwt_trusted_issuers: str = "api-gateway"

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

    human_review_sla_target_s: int | None = None
    case_report_max_chars: int = 4000

    tick_secret: str = ""
    demo_mode: bool = True
    log_level: str = "INFO"


settings = Settings()
