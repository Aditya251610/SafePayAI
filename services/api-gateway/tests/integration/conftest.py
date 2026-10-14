"""Integration-only fixtures: real Postgres (test-container pattern), app client,
db helpers. Expects `PS_APIGATEWAY_TEST_DATABASE_URL`, defaulting to port 5432 -
matching the `postgres:16` service container ci-python-service.yml actually starts
(and every other service's test convention). An earlier draft of this file defaulted
to 55432 under a mistaken assumption about CI's port; fixed."""

from __future__ import annotations

import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

TEST_DATABASE_URL = os.environ.get(
    "PS_APIGATEWAY_TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres",
)


@pytest.fixture(autouse=True)
def _db_env(monkeypatch):
    monkeypatch.setenv("PS_APIGATEWAY_DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("PS_APIGATEWAY_MIGRATION_DATABASE_URL", TEST_DATABASE_URL)

    import app.db as db_module

    db_module._engine = None
    db_module._session_factory = None
    yield
    db_module._engine = None
    db_module._session_factory = None


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(TEST_DATABASE_URL)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables(db_engine, _db_env):
    async with db_engine.begin() as conn:
        await conn.execute(
            text(
                'TRUNCATE "gateway"."sessions", "gateway"."csrf_uses", "gateway"."users" CASCADE'
            )
        )
    yield


@pytest_asyncio.fixture
async def app_client():
    from app.main import app

    transport = ASGITransport(app=app)
    # https:// base_url so Secure cookies the gateway sets are actually stored and
    # replayed by httpx's cookie jar across requests in a test (Secure cookies are
    # dropped for http:// by stdlib cookiejar semantics).
    async with AsyncClient(
        transport=transport, base_url="https://testserver"
    ) as client:
        yield client


@pytest_asyncio.fixture
async def make_user(db_engine):
    async def _make(
        *,
        handle: str | None,
        role: str,
        actor_type: str,
        display_name: str | None = None,
        password_hash: str | None = None,
        is_ephemeral: bool = False,
        epoch: int = 0,
        merchant_id: str | None = None,
    ) -> dict:
        async with db_engine.begin() as conn:
            row = (
                await conn.execute(
                    text(
                        """
                        INSERT INTO "gateway"."users"
                            (handle, role, actor_type, display_name, password_hash,
                             is_ephemeral, epoch, merchant_id)
                        VALUES (:handle, :role, :actor_type, :display_name,
                                :password_hash, :is_ephemeral, :epoch, :merchant_id)
                        RETURNING id, epoch
                        """
                    ),
                    {
                        "handle": handle,
                        "role": role,
                        "actor_type": actor_type,
                        "display_name": display_name,
                        "password_hash": password_hash,
                        "is_ephemeral": is_ephemeral,
                        "epoch": epoch,
                        "merchant_id": merchant_id,
                    },
                )
            ).first()
        return {"id": str(row[0]), "epoch": row[1]}

    return _make
