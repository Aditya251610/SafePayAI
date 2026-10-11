"""Async engine/session factory for the audit service (asyncpg driver).

Reads `settings.database_url` (pooled Neon endpoint, runtime) per
service-skeleton-conventions.md sec 1. Migrations use `settings.migrate_database_url`
(direct endpoint) via migrations/env.py, never via this module.

Deviation note: audit's own spec.md sec 0/3 names the driver as "psycopg 3 (ADR-002)",
but service-skeleton-conventions.md sec 7 (pyproject template, generic across all 11
services) pins `asyncpg`. The conventions doc explicitly covers the dependency list, so
it wins per this wave's binding rule; flagged for the audit/platform owner to reconcile
ADR-002 against the Wave 4 template if psycopg 3 is actually required.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.settings import get_settings

logger = logging.getLogger("audit.db")

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Lazily builds the pooled async engine.

    pool_pre_ping / small pool / pool_recycle per data-architecture.md sec 9 (Neon
    scale-to-zero + PgBouncer transaction-mode guidance). Statement cache disabled
    because transaction-mode poolers don't retain prepared statements (spec.md sec 3).
    """
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=3,
            pool_recycle=300,
            connect_args={"statement_cache_size": 0},
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncSession:
    """FastAPI dependency: yields a short-lived AsyncSession.

    Wave 4: wiring only, no queries issued here. Wave 5 adds the advisory-lock append
    path, verify streaming, and grid queries (spec.md sec 3/7/9).
    """
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def check_db_ready(
    retries: int = 3, backoff_seconds: float = 0.25
) -> tuple[bool, str | None]:
    """SELECT 1 against the pooled connection with retry/backoff.

    Matches data-architecture.md sec 9's pre_ping pattern and api.md sec 6's /readyz
    contract (DB reachable). Wave 5 additionally checks genesis-row presence and trusted
    issuers loaded (api.md sec 6); not implemented here yet.
    """
    engine = get_engine()
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True, None
        except Exception as exc:  # pragma: no cover - network/db dependent
            last_error = exc
            logger.warning("readyz db check failed (attempt %s/%s): %s", attempt + 1, retries, exc)
            await asyncio.sleep(backoff_seconds * (2**attempt))
    return False, type(last_error).__name__ if last_error else "unknown_error"


async def dispose_engine() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
