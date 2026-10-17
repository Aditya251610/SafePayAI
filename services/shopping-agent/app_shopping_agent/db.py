"""Async engine/session factory. Pooled endpoint for runtime, direct URL for migrations.
Per data-architecture.md section 9: pre_ping on checkout, pool_size=2, max_overflow=3,
pool_recycle=300.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app_shopping_agent.settings import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.db_url,
    pool_size=2,
    max_overflow=3,
    pool_recycle=300,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
