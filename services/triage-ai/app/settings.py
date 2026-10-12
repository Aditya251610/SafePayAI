"""Settings for triage-ai (Wave 4 skeleton).

Env prefix PS_TRIAGEAI_ per docs/service-skeleton-conventions.md section 2. Names copied
verbatim from services/triage-ai/{spec.md section 12, deployment.md section 4}. Per
ADR-010, this service holds LLM provider keys — but Wave 4 wires no real provider calls
(provider adapter raises NotImplementedError; see app/llm_provider.py).
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from safepayai_common.outbox import DEV_AUDIT_RELAY_KID, DEV_AUDIT_RELAY_PRIVATE_KEY_PEM


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PS_TRIAGEAI_", extra="ignore")

    service_name: str = "triage-ai"
    env: str = "dev"

    database_url: str = ""

    llm_enabled: bool = True
    min_confidence: float = 0.7
    max_text_chars: int = 1000
    prompt_version: str = "v1"

    timeout_classify_s: float = 4.0
    timeout_draft_s: float = 6.0
    timeout_brief_s: float = 10.0

    stale_window_hours: int = 48

    max_calls_per_case: int = 6
    cache_ttl_hours: int = 24
    debug_log_prompts: bool = False

    llm_provider_primary: str = "groq"
    llm_provider_fallback: str = "gemini"
    llm_model_triage_primary: str = ""
    llm_model_triage_fallback: str = ""

    # Provider secrets: physically read inside the shared `ai` process env in Profile B,
    # but kept PS_TRIAGEAI_-prefixed per the platform-wide convention (deployment.md section 4).
    gemini_api_key: str = ""
    groq_api_key: str = ""

    internal_jwks_url: str = ""
    internal_jwt_audience: str = "triage-ai"
    internal_allowed_callers: str = "resolution"

    audit_push_url: str = ""
    internal_event_hmac_key: str = ""

    # Outbox relay (S2-06): see mandate/app/settings.py for the full rationale comment.
    outbox_relay_audit_base_url: str = "http://localhost:8000"
    outbox_relay_jwt_kid: str = DEV_AUDIT_RELAY_KID
    outbox_relay_jwt_issuer: str = "ps-triage-ai"
    outbox_relay_jwt_private_key: str = DEV_AUDIT_RELAY_PRIVATE_KEY_PEM
    outbox_relay_batch_size: int = 100

    # Bare-name exception (shared cron-trigger secret; conventions doc section 2) -- guards
    # /internal/outbox/flush, which the scheduled workflow calls directly (not via JWKS).
    internal_tick_secret: str = Field(default="", alias="INTERNAL_TICK_SECRET")

    log_level: str = "INFO"


settings = Settings()
