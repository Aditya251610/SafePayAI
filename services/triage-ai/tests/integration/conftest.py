"""Integration fixtures: a real throwaway Postgres database, migrated from scratch with
`alembic upgrade head`, exercised through the real app over the runtime role `svc_triage`
(not the superuser). Mirrors services/shopping-agent/tests/integration/conftest.py's pattern.
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
TEST_DB_NAME = os.environ.get("TEST_PG_DB_NAME", "triage_ai_test")
DEV_DB_PASSWORD = os.environ.get("PS_TRIAGEAI_DEV_DB_PASSWORD", "changeme")

MIGRATION_URL = f"postgresql+asyncpg://postgres:postgres@localhost:5432/{TEST_DB_NAME}"
RUNTIME_URL = (
    f"postgresql+asyncpg://svc_triage:{DEV_DB_PASSWORD}@localhost:5432/{TEST_DB_NAME}"
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
    env["PS_TRIAGEAI_MIGRATION_DATABASE_URL"] = MIGRATION_URL
    env["PS_TRIAGEAI_DATABASE_URL"] = MIGRATION_URL
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
                f"ALTER ROLE svc_triage WITH PASSWORD '{DEV_DB_PASSWORD}'"
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
    # app/settings.py builds a module-level `settings = Settings()` singleton that only ever
    # reads os.environ once, the first time app.settings is imported in this process -- and
    # unit tests (test_llm_provider.py) import the `Settings` CLASS directly, which also
    # triggers that same module-level singleton line, before this fixture ever runs. Setting
    # the env var here is not enough on its own if app.settings (and therefore app.db, whose
    # module-level engine is built from settings.database_url) was already imported earlier
    # in this same pytest process. Purge any already-cached app.* modules so the import below
    # re-executes fresh, with the env var actually in place.
    import sys

    for mod_name in list(sys.modules):
        if mod_name == "app" or mod_name.startswith("app."):
            del sys.modules[mod_name]

    os.environ["PS_TRIAGEAI_DATABASE_URL"] = migrated_db

    from app.db import engine as app_engine
    from app.main import app as fastapi_app

    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app), base_url="http://test"
    ) as ac:
        yield ac

    await app_engine.dispose()
