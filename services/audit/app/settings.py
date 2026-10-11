"""Pydantic-settings configuration for the audit service.

Env prefix: PS_AUDIT_ (service-skeleton-conventions.md sec 2). Every field below maps to a
name already documented in .claude/prd/services/audit/{spec.md sec 15, deployment.md sec 4},
EXCEPT `batch_max`, which is referenced by api.md sec 1 ("PS_AUDIT_BATCH_MAX envelopes") but
is NOT listed in spec.md sec 15 / deployment.md sec 4's env tables. Flagged here rather than
silently added only in code (service-skeleton-conventions.md sec 2): a doc owner should add
PS_AUDIT_BATCH_MAX to spec.md sec 15 and deployment.md sec 4 to close the gap.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PS_AUDIT_", env_file=".env", extra="ignore")

    # --- Database (deployment.md sec 2/4) ---
    # Pooled Neon endpoint, audit_app role. Placeholder only; real value lives in the
    # platform secret store, never in this repo (context-brief.md sec 5).
    database_url: str = "postgresql+asyncpg://audit_app:changeme@localhost:5432/artiq"
    # Direct Neon endpoint, audit_owner/mig_audit role. CI/migration-only; must never be
    # set in the same env as database_url at runtime (spec.md sec 8, checked in main.py).
    migrate_database_url: str | None = None
    db_pool_max: int = 5

    # --- Chain identity and environment guard ---
    chain_id: str = "ps-demo-1"
    env: str = "dev"  # dev|ci|demo|prod (spec.md sec 15); guards scripts/tamper_demo.py

    # --- Auth (spec.md sec 5/8: static trusted-issuer map, no network JWKS fetch) ---
    # Inline JSON or a filesystem path to a JSON map of {issuer: {kid: {public_key, alg}}}.
    # Falls back to app/auth_fixtures/local_jwks.json for standalone Wave 4 runs when unset
    # (service-skeleton-conventions.md sec 5: "point it at a local static JWKS fixture if
    # the gateway isn't implemented yet").
    trusted_issuers: str | None = None
    internal_audience: str = "audit"
    emission_allowlist_path: str | None = None

    # --- Head export signing (P1, optional) ---
    head_signing_key: str | None = None
    head_signing_key_id: str | None = None

    # --- Verify / append tuning ---
    verify_chunk: int = 500
    append_max_retries: int = 3
    page_max: int = 100

    # --- Flagged, undocumented-but-referenced (see module docstring) ---
    batch_max: int = 100

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
