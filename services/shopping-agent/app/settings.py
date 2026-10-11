"""Settings for shopping-agent. Env prefix PS_SHOPPINGAGENT_ per
docs/service-skeleton-conventions.md section 2. Values come from
.claude/prd/services/shopping-agent/{spec,deployment}.md section 10 / section 4.

No PAYPAL_* variable may ever appear here (ADR-010); see test in tests/unit
that asserts the manifest is clean.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PS_SHOPPINGAGENT_",
        env_file=".env",
        extra="ignore",
    )

    service_name: str = "shopping-agent"
    log_level: str = "info"

    # LLM gateway (ADR-010: only shopping-agent and triage-ai hold these keys)
    llm_enabled: bool = True
    llm_provider: str = "gemini"
    llm_fallback_provider: str = "groq"
    llm_model_cart: str | None = None
    llm_model_cart_fallback: str | None = None
    llm_model_fit: str | None = None
    llm_model_fit_fallback: str | None = None
    gemini_api_key: str | None = None
    groq_api_key: str | None = None
    llm_timeout_cart_s: float = 6.0
    llm_timeout_fit_s: float = 4.0
    llm_wall_budget_s: float = 8.0
    llm_temperature_cart: float = 0.0
    llm_temperature_fit: float = 0.0
    llm_max_output_cart: int = 400
    llm_max_output_fit: int = 200
    llm_daily_cap_pct: int = 70
    max_cart_calls: int = 2
    max_fit_calls: int = 1
    intent_max_chars: int = 500
    untrusted_max_chars: int = 1000
    prompt_version_cart: str = "cart.v1"
    prompt_version_fit: str = "fit.v1"
    cache_ttl_hours: int = 24
    fit_min_confidence: float = 0.6

    # Database (schema `agent`; role svc_agent per data-architecture.md section 4)
    db_url: str = "postgresql+asyncpg://svc_agent:changeme@localhost:5432/artiq"
    # NOTE: not in deployment.md's documented env table (only PS_SHOPPINGAGENT_DB_URL is listed
    # there); added here because Alembic migrations need a direct (non-pooled) connection per
    # data-architecture.md section 8. Flagged in the scaffolding handoff report, not silently added.
    migration_db_url: str = "postgresql+asyncpg://mig_agent:changeme@localhost:5432/artiq"

    # Peers (Profile B: in-process; Profile A: HTTP base URLs)
    catalog_base_url: str = "http://localhost:8000"
    mandate_base_url: str = "http://localhost:8000"
    audit_events_url: str = "http://localhost:8000"

    # Internal auth (auth-gateway.md; stub JWKS fixture until the gateway exists)
    internal_jwks_url: str = "http://localhost:8080/.well-known/jwks.json"
    service_audience: str = "shopping-agent"


def get_settings() -> Settings:
    return Settings()
