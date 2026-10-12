"""Async engine/session factory. Per data-architecture.md section 9: pre_ping on checkout,
pool_size=2, max_overflow=3, pool_recycle=300.

Lazily constructed (mirrors services/mandate/app/db.py and services/audit/app/db.py's
`get_engine()`/`get_session_factory()` pattern, not services/checkout's eager module-level
`engine = create_async_engine(...)`): an eager engine built from `get_settings()` at import
time bakes in whatever PS_PAYPALADAPTER_DATABASE_URL happens to be set when this module is
*first* imported anywhere in the process. In a single pytest process that runs both unit and
integration tests together (`pytest tests/unit tests/integration`), a unit test importing
`app.main`/`app.mcp` before the integration suite's `pg_env` fixture sets the real throwaway-
database env vars would otherwise permanently poison the engine for every later integration
test in that process -- caught by running exactly that combined command twice in a row.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.settings import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.db_url,
            pool_size=2,
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


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_session_factory()() as session:
        yield session
