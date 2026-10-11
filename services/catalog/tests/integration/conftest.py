"""Integration test fixtures: real Postgres (docker-compose's `postgres` service, or
any Postgres reachable via TEST_PG_ADMIN_URL), migrated from scratch with
`alembic upgrade head`, then exercised through the real app over the runtime role
`svc_catalog` - the same role the deployed service uses (not the superuser), so these
tests also exercise the grants (spec.md section 1 / IT2-class checks).

Mirrors ci-python-service.yml's integration job shape (migrate, then pytest), but
targets a dedicated `catalog_test` database so it is safe to run next to a live
docker-compose stack.
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
TEST_DB_NAME = os.environ.get("TEST_PG_DB_NAME", "catalog_test")
DEV_DB_PASSWORD = os.environ.get("PS_CATALOG_DEV_DB_PASSWORD", "changeme")

MIGRATION_URL = f"postgresql+asyncpg://postgres:postgres@localhost:5432/{TEST_DB_NAME}"
RUNTIME_URL = (
    f"postgresql+asyncpg://svc_catalog:{DEV_DB_PASSWORD}@localhost:5432/{TEST_DB_NAME}"
)


def _asyncpg_dsn(url: str) -> str:
    """asyncpg.connect() wants a bare `postgresql://` DSN, not SQLAlchemy's
    `postgresql+asyncpg://` driver-qualified form."""
    return url.replace("postgresql+asyncpg://", "postgresql://")


@pytest.fixture(scope="session")
def migrated_db() -> str:
    """Drops/recreates `catalog_test` and runs every migration against it, via a
    subprocess so the migration env's own asyncio.run() doesn't collide with pytest's
    event loop. Returns the runtime (svc_catalog) DSN."""
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
    env["PS_CATALOG_MIGRATION_DATABASE_URL"] = MIGRATION_URL
    env["PS_CATALOG_DEV_DB_PASSWORD"] = DEV_DB_PASSWORD
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=SERVICE_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,  # asserted explicitly below, with stdout/stderr in the message
    )
    assert result.returncode == 0, (
        f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}"
    )
    return RUNTIME_URL


@pytest_asyncio.fixture
async def db_engine(migrated_db: str):
    engine = create_async_engine(migrated_db, pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def admin_conn(migrated_db: str):
    """Superuser connection for test-only setup (e.g. flipping an item's `active`
    flag) that the read-only runtime role is deliberately not allowed to do."""
    engine = create_async_engine(MIGRATION_URL)
    async with engine.connect() as conn:
        yield conn
        await conn.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(migrated_db: str):
    os.environ["PS_CATALOG_DATABASE_URL"] = migrated_db

    # Reset app/db.py's module-level engine cache so it picks up the test DSN even if
    # another test module (or a prior run in this process) already initialized it.
    import app.db as db_module

    db_module._engine = None
    db_module._session_factory = None

    from app.deps import Principal, verify_internal_jwt
    from app.main import app

    default_principal = Principal(
        sub="test-caller", role="checkout", jti="test-jti", scope=[]
    )
    app.dependency_overrides[verify_internal_jwt] = lambda: default_principal

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as http_client:
        yield http_client

    app.dependency_overrides.clear()
