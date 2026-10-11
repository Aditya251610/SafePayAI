"""Settings for tracking (Wave 4 skeleton).

Env prefix PS_TRACKING_ per docs/service-skeleton-conventions.md section 2, with two
documented bare-name exceptions used by this service: INTERNAL_TICK_SECRET (shared
cron-trigger name, this service has /internal/tick) and the DB url name which this
service's own deployment.md/spec.md document as PS_TRACKING_DB_URL (not *_DATABASE_URL).
Names are copied verbatim from services/tracking/{spec,deployment}.md section 9 / env list.
No values, no secrets here.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PS_TRACKING_", extra="ignore")

    service_name: str = "tracking"

    # Database (direct per-service convention name, see deployment.md)
    db_url: str = Field(default="", alias="PS_TRACKING_DB_URL")
    migration_db_url: str = Field(default="", alias="PS_TRACKING_MIGRATION_DB_URL")

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

    # Auth (internal service-JWT verification, see deps.py)
    internal_jwks_url: str = ""
    internal_audience: str = "tracking"

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
