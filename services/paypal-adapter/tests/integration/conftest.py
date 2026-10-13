"""L3 integration fixtures: a real throwaway Postgres database (never SQLite), the real
Alembic migration (exercising the schema-bootstrap-commit fix and grants), a static
trusted-issuer JWT fixture, and an ASGI test client. Mirrors services/mandate/tests/conftest.py.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid

import asyncpg
import jwt
import pytest
from httpx import ASGITransport, AsyncClient

ADMIN_DSN = os.environ.get(
    "TEST_PG_ADMIN_DSN", "postgresql://postgres:postgres@localhost:5432/postgres"
)
SERVICE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_SECRET = "test-only-hs256-secret-not-for-production-use"
TEST_KID = "test-kid"


def _asyncpg_dsn(db: str, user: str = "postgres", password: str = "postgres") -> str:
    return f"postgresql://{user}:{password}@localhost:5432/{db}"


def _sqlalchemy_dsn(db: str, user: str, password: str) -> str:
    return f"postgresql+asyncpg://{user}:{password}@localhost:5432/{db}"


@pytest.fixture(scope="session")
def test_db_name():
    return f"paypaladapter_test_{uuid.uuid4().hex[:12]}"


@pytest.fixture(scope="session")
async def pg_env(test_db_name):
    admin_conn = await asyncpg.connect(dsn=ADMIN_DSN)
    try:
        await admin_conn.execute(f'DROP DATABASE IF EXISTS "{test_db_name}"')
        await admin_conn.execute(f'CREATE DATABASE "{test_db_name}"')
    finally:
        await admin_conn.close()

    db_conn = await asyncpg.connect(dsn=_asyncpg_dsn(test_db_name))
    try:
        await db_conn.execute('CREATE SCHEMA IF NOT EXISTS "paypal"')
    finally:
        await db_conn.close()

    migration_url = _sqlalchemy_dsn(test_db_name, "postgres", "postgres")
    env = os.environ.copy()
    env["PS_PAYPALADAPTER_MIGRATION_DATABASE_URL"] = migration_url
    env["PS_PAYPALADAPTER_DATABASE_URL"] = migration_url
    result = subprocess.run(  # noqa: ASYNC221 - one-time session setup, not request-path code
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=SERVICE_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"alembic upgrade failed:\n{result.stdout}\n{result.stderr}"

    svc_password = "svc_paypal_test_pw"  # noqa: S105 - test-only, throwaway DB
    admin_conn = await asyncpg.connect(dsn=_asyncpg_dsn(test_db_name))
    try:
        await admin_conn.execute(f"ALTER ROLE svc_paypal WITH PASSWORD '{svc_password}'")
        # The baseline migration seeds control_flags fail-closed (frozen=true, see
        # app.control_flags / app.ops._money_frozen's static-env-OR-DB-flag check added
        # alongside the get_capture/tracking/control wave). This test suite's
        # PS_PAYPALADAPTER_MONEY_ENABLED=true below is a deliberate "money enabled for this
        # test run" signal -- unfreeze the service-local DB flag to match, same as a real
        # deployment would via POST /v1/control/unfreeze.
        await admin_conn.execute("UPDATE paypal.control_flags SET frozen = false WHERE id = 1")
    finally:
        await admin_conn.close()

    env_vars = {
        "PS_PAYPALADAPTER_DATABASE_URL": _sqlalchemy_dsn(test_db_name, "svc_paypal", svc_password),
        "PS_PAYPALADAPTER_MIGRATION_DATABASE_URL": migration_url,
        "PAYPAL_CLIENT_ID": "test-client-id",
        "PAYPAL_CLIENT_SECRET": "test-client-secret",  # noqa: S105
        "PS_PAYPALADAPTER_INTERNAL_TRUSTED_ISSUERS": json.dumps({TEST_KID: TEST_SECRET}),
        "PS_PAYPALADAPTER_INTERNAL_JWT_AUD": "paypal-adapter",
        "PS_PAYPALADAPTER_MONEY_ENABLED": "true",
        "PS_PAYPALADAPTER_PAYPAL_RETURN_URL_ALLOWED_ORIGINS": "http://localhost:3000",
    }
    for k, v in env_vars.items():
        os.environ[k] = v

    yield {"db_name": test_db_name}

    admin_conn = await asyncpg.connect(dsn=ADMIN_DSN)
    try:
        await admin_conn.execute(f'DROP DATABASE IF EXISTS "{test_db_name}" WITH (FORCE)')
    finally:
        await admin_conn.close()


@pytest.fixture(scope="session")
def app(pg_env):
    from app.main import app as fastapi_app

    return fastapi_app


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def db_conn(pg_env):
    conn = await asyncpg.connect(dsn=_asyncpg_dsn(pg_env["db_name"]))
    try:
        yield conn
    finally:
        await conn.close()


@pytest.fixture(autouse=True)
async def _clean_tables(pg_env):
    conn = await asyncpg.connect(dsn=_asyncpg_dsn(pg_env["db_name"]))
    try:
        await conn.execute(
            "TRUNCATE paypal.outbox, paypal.ticket_nonces, paypal.refund_ledger, paypal.call_ledger"
        )
    finally:
        await conn.close()
    yield


def mint_token(sub: str, *, aud: str = "paypal-adapter") -> str:
    now = int(time.time())
    payload = {"sub": sub, "aud": aud, "iat": now, "exp": now + 300}
    return jwt.encode(payload, TEST_SECRET, algorithm="HS256", headers={"kid": TEST_KID})


@pytest.fixture
def checkout_token():
    return mint_token("checkout")


@pytest.fixture
def tracking_token():
    return mint_token("tracking")


@pytest.fixture
def resolution_token():
    return mint_token("resolution")


@pytest.fixture
def shopping_agent_token():
    return mint_token("shopping-agent")


@pytest.fixture
def triage_ai_token():
    return mint_token("triage-ai")
