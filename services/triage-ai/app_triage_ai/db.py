"""Async engine/session factory for triage-ai (schema `triage` only; no grant on any money
table, ADR-004/ADR-010)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app_triage_ai.settings import settings

engine = create_async_engine(
    settings.database_url or "postgresql+asyncpg://localhost/placeholder",
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
    import asyncio

    from sqlalchemy import text

    for attempt in range(retries):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:  # noqa: BLE001
            await asyncio.sleep(0.2 * (2**attempt))
    return False
