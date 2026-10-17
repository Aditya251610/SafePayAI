"""Async engine/session factory for tracking (schema `tracking`).

Wave 4: wiring only. Pooled URL for runtime (settings.db_url), direct URL for migrations
(settings.migration_db_url, used only by alembic env.py, not here). Pre_ping + retry per
data-architecture.md section 9 (cold-start tolerance on Neon-style scale-to-zero Postgres).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app_tracking.settings import settings

engine = create_async_engine(
    settings.db_url or "postgresql+asyncpg://localhost/placeholder",
    pool_pre_ping=True,
    pool_size=2,
    max_overflow=3,
    pool_recycle=300,
    future=True,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def ping_db(retries: int = 3) -> bool:
    """SELECT 1 against the pooled connection, 3 retries with backoff (conventions doc section 3)."""
    import asyncio

    from sqlalchemy import text

    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception as exc:  # noqa: BLE001 - readiness probe, deliberately broad
            last_exc = exc
            await asyncio.sleep(0.2 * (2**attempt))
    if last_exc is not None:
        return False
    return False
