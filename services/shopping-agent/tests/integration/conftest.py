"""Integration fixtures: a real throwaway Postgres database, migrated from scratch with
`alembic upgrade head`, exercised through the real app over the runtime role `svc_agent`
(not the superuser). Mirrors services/checkout/tests/integration/conftest.py's pattern.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

SERVICE_DIR = pathlib.Path(__file__).resolve().parents[2]

ADMIN_URL = os.environ.get(
    "TEST_PG_ADMIN_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres",
)
TEST_DB_NAME = os.environ.get("TEST_PG_DB_NAME", "shopping_agent_test")
DEV_DB_PASSWORD = os.environ.get("PS_SHOPPINGAGENT_DEV_DB_PASSWORD", "changeme")

MIGRATION_URL = f"postgresql+asyncpg://postgres:postgres@localhost:5432/{TEST_DB_NAME}"
RUNTIME_URL = (
    f"postgresql+asyncpg://svc_agent:{DEV_DB_PASSWORD}@localhost:5432/{TEST_DB_NAME}"
)


def _asyncpg_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


@pytest.fixture(scope="session")
def migrated_db() -> str:
    import anyio
    import asyncpg

    async def _reset() -> None:
        conn = await asyncpg.connect(_asyncpg_dsn(ADMIN_URL))
        try:
            await conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}"')
            await conn.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
        finally:
            await conn.close()

    anyio.run(_reset)

    env = os.environ.copy()
    env["PS_SHOPPINGAGENT_MIGRATION_DATABASE_URL"] = MIGRATION_URL
    env["PS_SHOPPINGAGENT_DEV_DB_PASSWORD"] = DEV_DB_PASSWORD
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=SERVICE_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}"
    )

    import anyio as _anyio
    import asyncpg as _asyncpg

    async def _set_password() -> None:
        conn = await _asyncpg.connect(_asyncpg_dsn(MIGRATION_URL))
        try:
            await conn.execute(
                f"ALTER ROLE svc_agent WITH PASSWORD '{DEV_DB_PASSWORD}'"
            )
        finally:
            await conn.close()

    _anyio.run(_set_password)

    return RUNTIME_URL


@pytest_asyncio.fixture
async def db_engine(migrated_db: str):
    engine = create_async_engine(migrated_db, pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def client(migrated_db: str):
    # app/db.py builds its engine from settings.db_url at import time, so the env var
    # must be set BEFORE app_shopping_agent.main (and therefore app_shopping_agent.db) is first imported. health.py
    # uses the module-level SessionLocal directly, not a Depends(get_db) override.
    os.environ["PS_SHOPPINGAGENT_DATABASE_URL"] = migrated_db

    from app_shopping_agent.db import engine as app_engine
    from app_shopping_agent.main import app as fastapi_app

    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app), base_url="http://test"
    ) as ac:
        yield ac

    await app_engine.dispose()
