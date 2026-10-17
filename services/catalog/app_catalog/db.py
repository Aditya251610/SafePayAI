"""Async engine/session factory for catalog (schema `catalog`, role `svc_catalog`).

Reads settings.database_url (pooled, runtime). Migrations use migration_database_url
(direct, role mig_catalog) and are driven from migrations/env.py, not from here.
Pool sized small per data-architecture.md section 9 (Neon free connection budget).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app_catalog.settings import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            pool_size=settings.db_pool_size,
            max_overflow=3,
            pool_recycle=300,
            pool_pre_ping=True,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yields a session, closes it after the request."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def ping() -> bool:
    """SELECT 1 against the pooled connection, used by /readyz. No retry/backoff
    logic here yet (Wave 5); conventions doc section 3 wants 3 retries with backoff."""
    from sqlalchemy import text

    engine = get_engine()
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return True
