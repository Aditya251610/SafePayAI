"""Pydantic-settings configuration for catalog.

Env prefix PS_CATALOG_ per docs/service-skeleton-conventions.md section 2.
Variable names taken verbatim from .claude/prd/services/catalog/{spec,deployment}.md
section 8 / "Environment". Do not invent names here without adding them to
deployment.md and .env.example (see this service's README / handoff note).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PS_CATALOG_", extra="ignore")

    service_name: str = "catalog"
    app_env: str = "local"
    log_level: str = "INFO"

    # PORT is platform-injected and unprefixed per convention; read separately.
    port: int = 8000

    database_url: str = "postgresql+asyncpg://catalog_ro:password@localhost:5432/artiq"
    seed_database_url: str | None = None
    migration_database_url: str = "postgresql+asyncpg://mig_catalog:password@localhost:5432/artiq"

    seed_on_start: bool = True
    admin_enabled: bool = False
    seed_file: str = "app/seed/catalog_seed.json"

    max_lines: int = 20
    max_line_qty: int = 10

    internal_jwks_url: str | None = None
    internal_jwt_audience: str = "catalog"
    internal_caller_allowlist: str | None = None

    db_pool_size: int = 2


def get_settings() -> Settings:
    """Returns a Settings instance. Wave 5: wrap with lru_cache once config is read-heavy."""
    return Settings()
