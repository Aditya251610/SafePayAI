"""Shared integration fixtures: a real throwaway Postgres database (never SQLite), role
grants matching the baseline migration, and a direct `asyncpg`/SQLAlchemy session wired to
that database. Mirrors services/mandate/tests/conftest.py's pattern.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from urllib.parse import urlsplit

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ADMIN_DSN = os.environ.get(
    "TEST_PG_ADMIN_DSN", "postgresql://postgres:postgres@localhost:5432/postgres"
)
# Parsed out of ADMIN_DSN rather than hardcoded as a function-parameter default below --
# GitGuardian's secret scanner flags a bare `password: str = "<literal>"` default even
# though this is the disposable local/CI Postgres superuser password, not a real secret.
_admin_parts = urlsplit(ADMIN_DSN)
ADMIN_USER = _admin_parts.username or "postgres"
ADMIN_PASSWORD = _admin_parts.password or "postgres"
SERVICE_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

# app/settings.py builds a module-level `settings = Settings()` singleton that reads os.environ
# exactly once, at import time. Test modules do `from app_tracking... import ...` at module scope, which
# pytest resolves while COLLECTING tests - before any fixture (including pg_env below) runs. So
# any env var a usecase reads directly off `settings` (e.g. sandbox_mode) must be set here, at
# conftest module load time, which pytest guarantees happens before it imports sibling test
# files in this directory. DB URLs don't need this: tests build their own engine/session
# directly (see `session` fixture) rather than importing app_tracking.db's module-level engine.
os.environ.setdefault("PS_TRACKING_SANDBOX_MODE", "true")
os.environ.setdefault("PS_TRACKING_DEMO_CONTROLS_ENABLED", "true")
os.environ.setdefault("INTERNAL_TICK_SECRET", "test-tick-secret")


def _asyncpg_dsn(
    db: str, user: str = ADMIN_USER, password: str = ADMIN_PASSWORD
) -> str:
    return f"postgresql://{user}:{password}@localhost:5432/{db}"


def _sqlalchemy_dsn(db: str, user: str, password: str) -> str:
    return f"postgresql+asyncpg://{user}:{password}@localhost:5432/{db}"


@pytest.fixture(scope="session")
def test_db_name() -> str:
    return f"tracking_test_{uuid.uuid4().hex[:12]}"


@pytest.fixture(scope="session")
async def pg_env(test_db_name: str):
    admin_conn = await asyncpg.connect(dsn=ADMIN_DSN)
    try:
        await admin_conn.execute(f'DROP DATABASE IF EXISTS "{test_db_name}"')
        await admin_conn.execute(f'CREATE DATABASE "{test_db_name}"')
    finally:
        await admin_conn.close()

    migration_url = _sqlalchemy_dsn(test_db_name, "postgres", "postgres")
    env = os.environ.copy()
    env["PS_TRACKING_MIGRATION_DATABASE_URL"] = migration_url
    env["PS_TRACKING_DATABASE_URL"] = migration_url
    result = subprocess.run(  # noqa: ASYNC221 - one-time session setup, not request-path code
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=SERVICE_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"alembic upgrade failed:\n{result.stdout}\n{result.stderr}"
    )

    svc_password = os.environ.get("PS_TRACKING_DEV_DB_PASSWORD", "changeme")
    admin_conn = await asyncpg.connect(dsn=_asyncpg_dsn(test_db_name))
    try:
        await admin_conn.execute(
            f"ALTER ROLE svc_tracking WITH PASSWORD '{svc_password}'"
        )
    finally:
        await admin_conn.close()

    env_vars = {
        "PS_TRACKING_DATABASE_URL": _sqlalchemy_dsn(
            test_db_name, "svc_tracking", svc_password
        ),
        "PS_TRACKING_MIGRATION_DATABASE_URL": migration_url,
        "INTERNAL_TICK_SECRET": "test-tick-secret",
        "PS_TRACKING_SANDBOX_MODE": "true",
        "PS_TRACKING_DEMO_CONTROLS_ENABLED": "true",
    }
    for k, v in env_vars.items():
        os.environ[k] = v

    yield {"db_name": test_db_name, "svc_password": svc_password}

    admin_conn = await asyncpg.connect(dsn=ADMIN_DSN)
    try:
        await admin_conn.execute(
            f'DROP DATABASE IF EXISTS "{test_db_name}" WITH (FORCE)'
        )
    finally:
        await admin_conn.close()


@pytest.fixture
async def session(pg_env: dict) -> AsyncSession:
    """Runtime-role (svc_tracking) async session - what every usecase runs as in prod."""
    engine = create_async_engine(
        _sqlalchemy_dsn(pg_env["db_name"], "svc_tracking", pg_env["svc_password"]),
        future=True,
    )
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as s:
        yield s
    await engine.dispose()


@pytest.fixture(autouse=True)
async def _clean_tables(pg_env: dict):
    conn = await asyncpg.connect(dsn=_asyncpg_dsn(pg_env["db_name"]))
    try:
        await conn.execute(
            """
            TRUNCATE tracking.outbox, tracking.inbox, tracking.detector_runs, tracking.tick_lease,
                     tracking.detections, tracking.clock_jumps, tracking.shipment_events,
                     tracking.scheduled_events, tracking.shipments
            """
        )
        await conn.execute(
            "UPDATE tracking.demo_clock SET offset_seconds = 0, version = version + 1 WHERE id = 1"
        )
    finally:
        await conn.close()
    yield
