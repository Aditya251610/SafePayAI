"""Shared test fixtures: a real throwaway Postgres database (never SQLite), role
grants matching the baseline migration, RSA-signed internal JWTs, and an ASGI
test client wired to that database.
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
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient

ADMIN_DSN = os.environ.get(
    "TEST_PG_ADMIN_DSN", "postgresql://postgres:postgres@localhost:5432/postgres"
)
SERVICE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _asyncpg_dsn(db: str, user: str = "postgres", password: str = "postgres") -> str:
    return f"postgresql://{user}:{password}@localhost:5432/{db}"


def _sqlalchemy_dsn(db: str, user: str, password: str) -> str:
    return f"postgresql+asyncpg://{user}:{password}@localhost:5432/{db}"


@pytest.fixture(scope="session")
def rsa_keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_pem, public_pem


@pytest.fixture(scope="session")
def test_db_name():
    return f"mandate_test_{uuid.uuid4().hex[:12]}"


@pytest.fixture(scope="session")
async def pg_env(rsa_keypair, test_db_name):
    """Creates a fresh database, runs the real Alembic migration against it (as the
    Postgres superuser, since role/schema creation needs CREATEROLE), sets a
    password on svc_mandate, and exports the env vars the app reads at runtime."""
    private_pem, public_pem = rsa_keypair

    admin_conn = await asyncpg.connect(dsn=ADMIN_DSN)
    try:
        await admin_conn.execute(f'DROP DATABASE IF EXISTS "{test_db_name}"')
        await admin_conn.execute(f'CREATE DATABASE "{test_db_name}"')
    finally:
        await admin_conn.close()

    # Alembic's version_table_schema="mandate" (migrations/env.py) needs the schema
    # to exist before it creates alembic_version; 0001_baseline also creates it
    # (idempotent IF NOT EXISTS), this just avoids an ordering dependency on when
    # Alembic itself creates its bookkeeping table relative to migration 0001.
    db_conn = await asyncpg.connect(dsn=_asyncpg_dsn(test_db_name))
    try:
        await db_conn.execute('CREATE SCHEMA IF NOT EXISTS "mandate"')
    finally:
        await db_conn.close()

    migration_url = _sqlalchemy_dsn(test_db_name, "postgres", "postgres")
    env = os.environ.copy()
    env["PS_MANDATE_MIGRATION_DATABASE_URL"] = migration_url
    env["PS_MANDATE_DATABASE_URL"] = (
        migration_url  # alembic env.py falls back to this if migration url unset
    )
    # Blocking subprocess.run in an async fixture is deliberate here: this is one-time
    # session setup (not request-path code), and alembic's own CLI entrypoint is the
    # simplest way to drive its async env.py without nesting event loops.
    result = subprocess.run(  # noqa: ASYNC221
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

    svc_password = "svc_mandate_test_pw"
    admin_conn = await asyncpg.connect(dsn=_asyncpg_dsn(test_db_name))
    try:
        await admin_conn.execute(
            f"ALTER ROLE svc_mandate WITH PASSWORD '{svc_password}'"
        )
    finally:
        await admin_conn.close()

    key_id = "k1"
    env_vars = {
        "PS_MANDATE_DATABASE_URL": _sqlalchemy_dsn(
            test_db_name, "svc_mandate", svc_password
        ),
        "PS_MANDATE_MIGRATION_DATABASE_URL": migration_url,
        "MANDATE_HMAC_KEY": "a" * 48,
        "MANDATE_HMAC_KEY_PREVIOUS": "b" * 48,
        "PS_MANDATE_HMAC_KEY_ID": key_id,
        "PS_MANDATE_HMAC_KEY_ID_PREVIOUS": "k0",
        "PS_MANDATE_TRUSTED_ISSUERS": json.dumps({key_id: public_pem}),
        "INTERNAL_TICK_SECRET": "test-tick-secret",
        "PS_MANDATE_SIGNING_ENABLED": "true",
    }
    for k, v in env_vars.items():
        os.environ[k] = v

    yield {
        "db_name": test_db_name,
        "private_pem": private_pem,
        "public_pem": public_pem,
        "key_id": key_id,
    }

    admin_conn = await asyncpg.connect(dsn=ADMIN_DSN)
    try:
        await admin_conn.execute(
            f'DROP DATABASE IF EXISTS "{test_db_name}" WITH (FORCE)'
        )
    finally:
        await admin_conn.close()


@pytest.fixture(scope="session")
def app(pg_env):
    from app_mandate.main import app as fastapi_app

    return fastapi_app


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def db_conn(pg_env):
    """Raw asyncpg connection as the Postgres superuser - used by tests to inspect
    rows directly or to assert DB-level immutability grants."""
    conn = await asyncpg.connect(dsn=_asyncpg_dsn(pg_env["db_name"]))
    try:
        yield conn
    finally:
        await conn.close()


@pytest.fixture
async def svc_conn(pg_env):
    """Raw asyncpg connection as svc_mandate - the actual runtime DB role, used by
    the immutability test (DB-level grant/trigger enforcement, not app-level)."""
    conn = await asyncpg.connect(
        dsn=_asyncpg_dsn(
            pg_env["db_name"], user="svc_mandate", password="svc_mandate_test_pw"
        )
    )
    try:
        yield conn
    finally:
        await conn.close()


@pytest.fixture(autouse=True)
async def _clean_tables(pg_env):
    """Truncates all mandate tables before every test for isolation."""
    conn = await asyncpg.connect(dsn=_asyncpg_dsn(pg_env["db_name"]))
    try:
        await conn.execute(
            """
            TRUNCATE mandate.outbox, mandate.idempotency_keys, mandate.nonce_uses, mandate.nonces,
                     mandate.protection_grants, mandate.spend_reservations, mandate.mandate_spend,
                     mandate.revocations, mandate.mandates, mandate.mandate_attestations
            """
        )
    finally:
        await conn.close()
    yield


def mint_token(
    private_pem: str,
    key_id: str,
    *,
    sub: str,
    role: str = "buyer",
    buyer_id: str | None = None,
    scope: list[str] | None = None,
) -> str:
    now = int(time.time())
    payload = {
        "iss": "api-gateway",
        "sub": sub,
        "aud": "mandate",
        "role": role,
        "jti": str(uuid.uuid4()),
        "scope": scope or [],
        "act": {"role": role, "actor_id": buyer_id or sub},
        "iat": now,
        "exp": now + 300,
    }
    return jwt.encode(payload, private_pem, algorithm="RS256", headers={"kid": key_id})


@pytest.fixture
def buyer_token(pg_env):
    def _make(buyer_id: str = "buyer-1"):
        return mint_token(
            pg_env["private_pem"],
            pg_env["key_id"],
            sub=buyer_id,
            role="buyer",
            buyer_id=buyer_id,
        )

    return _make


@pytest.fixture
def service_token(pg_env):
    def _make(sub: str = "svc:checkout"):
        return mint_token(
            pg_env["private_pem"], pg_env["key_id"], sub=sub, role="service"
        )

    return _make


@pytest.fixture
def merchant_token(pg_env):
    def _make(sub: str = "merchant-1"):
        return mint_token(
            pg_env["private_pem"], pg_env["key_id"], sub=sub, role="merchant"
        )

    return _make


@pytest.fixture
def reviewer_token(pg_env):
    def _make(sub: str = "reviewer-1"):
        return mint_token(
            pg_env["private_pem"], pg_env["key_id"], sub=sub, role="reviewer"
        )

    return _make
