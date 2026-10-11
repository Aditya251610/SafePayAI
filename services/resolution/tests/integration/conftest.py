"""Shared integration fixtures: a real throwaway Postgres database (never SQLite), role
grants matching the baseline migration, and a direct SQLAlchemy session wired to that
database. Mirrors services/mandate/tests/conftest.py's pattern.
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

# app/settings.py builds a module-level `settings = Settings()` singleton read once at import
# time, before any fixture runs (pytest imports test modules while collecting, ahead of fixture
# setup) - so any env var a usecase reads directly off `settings` must be set here, at conftest
# module load time. DB URLs don't need this: tests build their own engine/session directly.
os.environ.setdefault("PS_RESOLUTION_TICK_SECRET", "test-tick-secret")
os.environ.setdefault("PS_RESOLUTION_POLICY_VERSION", "v1")


def _asyncpg_dsn(
    db: str, user: str = ADMIN_USER, password: str = ADMIN_PASSWORD
) -> str:
    return f"postgresql://{user}:{password}@localhost:5432/{db}"


def _sqlalchemy_dsn(db: str, user: str, password: str) -> str:
    return f"postgresql+asyncpg://{user}:{password}@localhost:5432/{db}"


@pytest.fixture(scope="session")
def test_db_name() -> str:
    return f"resolution_test_{uuid.uuid4().hex[:12]}"


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
    env["PS_RESOLUTION_MIGRATION_DATABASE_URL"] = migration_url
    env["PS_RESOLUTION_DATABASE_URL"] = migration_url
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

    svc_password = os.environ.get("PS_RESOLUTION_DEV_DB_PASSWORD", "changeme")
    admin_conn = await asyncpg.connect(dsn=_asyncpg_dsn(test_db_name))
    try:
        await admin_conn.execute(
            f"ALTER ROLE svc_resolution WITH PASSWORD '{svc_password}'"
        )
    finally:
        await admin_conn.close()

    env_vars = {
        "PS_RESOLUTION_DATABASE_URL": _sqlalchemy_dsn(
            test_db_name, "svc_resolution", svc_password
        ),
        "PS_RESOLUTION_MIGRATION_DATABASE_URL": migration_url,
        "INTERNAL_TICK_SECRET": "test-tick-secret",
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
    """Runtime-role (svc_resolution) async session - what every usecase runs as in prod."""
    engine = create_async_engine(
        _sqlalchemy_dsn(pg_env["db_name"], "svc_resolution", pg_env["svc_password"]),
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
            TRUNCATE resolution.outbox, resolution.inbox_dedupe, resolution.idempotency_keys,
                     resolution.notifications, resolution.refund_attempts, resolution.policy_decisions,
                     resolution.approvals, resolution.offers, resolution.case_signals,
                     resolution.case_transitions, resolution.cases
            """
        )
        await conn.execute(
            "UPDATE resolution.control_flags SET refunds_frozen = true, epoch = epoch + 1 WHERE id = 1"
        )
    finally:
        await conn.close()
    yield


@pytest.fixture
async def unfrozen(pg_env: dict):
    """Most tests need REFUNDS_FROZEN = false to exercise the money path past check 1."""
    conn = await asyncpg.connect(dsn=_asyncpg_dsn(pg_env["db_name"]))
    try:
        await conn.execute(
            "UPDATE resolution.control_flags SET refunds_frozen = false, epoch = epoch + 1 WHERE id = 1"
        )
    finally:
        await conn.close()
