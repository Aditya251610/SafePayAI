"""Settings for shopping-agent. Env prefix PS_SHOPPINGAGENT_ per
docs/service-skeleton-conventions.md section 2. Values come from
.claude/prd/services/shopping-agent/{spec,deployment}.md section 10 / section 4.

No PAYPAL_* variable may ever appear here (ADR-010); see test in tests/unit
that asserts the manifest is clean.
"""

from __future__ import annotations

from pydantic import Field
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
    # PROVISIONAL stopgap only (build spec section 5): 0.6 is NOT a tuned value. Raw LLM
    # confidence is frequently miscalibrated/compressed regardless of correctness; this
    # floor must be re-derived from the eval harness's per-provider confidence-vs-
    # accuracy curve (scripts/run_agent_eval.py) before it is trusted as a real gate,
    # and re-derived again on any prompt/model version change. Never report this number
    # as tuned until that calibration has actually been run against real API keys.
    fit_min_confidence: float = 0.6

    # Database (schema `agent`; role svc_agent per data-architecture.md section 4)
    # NOTE: deployment.md section 2 documents PS_SHOPPINGAGENT_DB_URL, but CLAUDE.md's
    # repo-wide convention and ci-python-service.yml's exported env vars both use
    # PS_<SLUG>_DATABASE_URL -- that's a PRD/CI mismatch (not fixed here), and the
    # DATABASE_URL form is what actually has to match for CI to pass. Explicit alias used
    # so migrations aren't silently skipped and falling back to this dev default.
    db_url: str = Field(
        default="postgresql+asyncpg://svc_agent:changeme@localhost:5432/artiq",
        alias="PS_SHOPPINGAGENT_DATABASE_URL",
    )
    migration_db_url: str = Field(
        default="postgresql+asyncpg://mig_agent:changeme@localhost:5432/artiq",
        alias="PS_SHOPPINGAGENT_MIGRATION_DATABASE_URL",
    )

    # Peers (Profile B: in-process; Profile A: HTTP base URLs)
    catalog_base_url: str = "http://localhost:8000"
    mandate_base_url: str = "http://localhost:8000"
    audit_events_url: str = "http://localhost:8000"

    # Internal auth (auth-gateway.md; stub JWKS fixture until the gateway exists)
    internal_jwks_url: str = "http://localhost:8080/.well-known/jwks.json"
    service_audience: str = "shopping-agent"


def get_settings() -> Settings:
    return Settings()
