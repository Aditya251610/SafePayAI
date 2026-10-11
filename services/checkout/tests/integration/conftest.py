"""Integration fixtures: real Postgres, migrated via `alembic upgrade head`, exercised
through the real app over the runtime role `svc_checkout`. Mirrors
services/catalog/tests/integration/conftest.py's pattern.
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
TEST_DB_NAME = os.environ.get("TEST_PG_DB_NAME", "checkout_test")
DEV_DB_PASSWORD = os.environ.get("PS_CHECKOUT_DEV_DB_PASSWORD", "changeme")

MIGRATION_URL = f"postgresql+asyncpg://postgres:postgres@localhost:5432/{TEST_DB_NAME}"
RUNTIME_URL = (
    f"postgresql+asyncpg://svc_checkout:{DEV_DB_PASSWORD}@localhost:5432/{TEST_DB_NAME}"
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
    env["PS_CHECKOUT_MIGRATION_DATABASE_URL"] = MIGRATION_URL
    env["PS_CHECKOUT_DEV_DB_PASSWORD"] = DEV_DB_PASSWORD
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

    async def _set_password() -> None:
        conn = await asyncpg.connect(_asyncpg_dsn(MIGRATION_URL))
        try:
            await conn.execute(
                f"ALTER ROLE svc_checkout WITH PASSWORD '{DEV_DB_PASSWORD}'"
            )
        finally:
            await conn.close()

    anyio.run(_set_password)

    return RUNTIME_URL


@pytest_asyncio.fixture
async def db_engine(migrated_db: str):
    engine = create_async_engine(migrated_db, pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def client(migrated_db: str):
    os.environ["PS_CHECKOUT_DATABASE_URL"] = migrated_db

    import app.db as db_module
    from app.db import SessionLocal, engine
    from app.settings import get_settings

    settings = get_settings()
    settings.db_url = migrated_db
    new_engine = create_async_engine(
        migrated_db, pool_size=2, max_overflow=3, pool_pre_ping=True
    )
    from sqlalchemy.ext.asyncio import async_sessionmaker

    db_module.engine = new_engine
    db_module.SessionLocal = async_sessionmaker(new_engine, expire_on_commit=False)

    from app.deps import Principal, require_service_jwt
    from app.main import app

    default_principal = Principal(
        sub="test-buyer",
        role="buyer",
        buyer_id="11111111-1111-1111-1111-111111111111",
    )
    app.dependency_overrides[require_service_jwt] = lambda: default_principal

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as http_client:
        yield http_client

    app.dependency_overrides.clear()
    await new_engine.dispose()
    db_module.engine = engine
    db_module.SessionLocal = SessionLocal
