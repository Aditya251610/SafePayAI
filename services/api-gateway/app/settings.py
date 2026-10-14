"""Pydantic-settings configuration for api-gateway.

Env prefix PS_APIGATEWAY_ per docs/service-skeleton-conventions.md section 2.
Variable names taken verbatim from .claude/prd/services/api-gateway/spec.md section
13 and deployment.md section 5. `SEED_*` passwords are read only by scripts/seed,
never by the running app, and are intentionally NOT in this Settings class.
"""

from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from safepayai_common.startup_guard import assert_no_placeholder_secrets


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PS_APIGATEWAY_", extra="ignore")

    app_env: str = "local"
    demo_mode: bool = False
    log_level: str = "INFO"
    port: int = 8000

    database_url: str = (
        "postgresql+asyncpg://svc_apigateway:password@localhost:5432/artiq"
    )
    migration_database_url: str = (
        "postgresql+asyncpg://mig_apigateway:password@localhost:5432/artiq"
    )

    frontend_origins: str = "http://localhost:3000"
    cookie_name: str = "__Host-ps_sid"

    session_ttl_buyer_s: int = 7200
    session_cap_buyer_s: int = 28800
    session_ttl_staff_s: int = 3600
    max_ephemeral_buyers: int = 500

    csrf_key: str = "dev-only-change-me"
    csrf_ttl_s: int = 3600
    session_cookie_key: str | None = None

    signing_key_pem: str | None = None
    signing_kid: str = "k1"
    previous_public_keys: str | None = None
    internal_token_ttl_s: int = 60

    upstream_mode: str = "http"
    upstream_mandate_url: str | None = None
    upstream_catalog_url: str | None = None
    upstream_shopping_agent_url: str | None = None
    upstream_checkout_url: str | None = None
    upstream_tracking_url: str | None = None
    upstream_resolution_url: str | None = None
    upstream_audit_url: str | None = None

    upstream_connect_timeout_s: float = 5.0
    upstream_read_timeout_s: float = 10.0
    upstream_total_budget_s: float = 100.0
    upstream_retries: int = 1

    max_body_bytes: int = 1_000_000
    llm_daily_budget_calls: int = 500

    money_routes_enabled: bool = True
    tick_secret: str | None = None
    trusted_proxy_count: int = 0
    approval_url_host_allowlist: str | None = None

    sentry_dsn: str | None = None

    @model_validator(mode="after")
    def _no_placeholder_secrets(self) -> Settings:
        assert_no_placeholder_secrets(
            {
                "PS_APIGATEWAY_CSRF_KEY": self.csrf_key,
                "PS_APIGATEWAY_TICK_SECRET": self.tick_secret,
            }
        )
        return self


def get_settings() -> Settings:
    return Settings()
