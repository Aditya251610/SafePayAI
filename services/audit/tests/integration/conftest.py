"""L3 integration fixtures: real Postgres, real Alembic migration, real grants/triggers.

Per test-plan.md sec 1 "must run against real Postgres, not SQLite, to exercise role
grants and triggers". Uses the local docker-compose `postgres` service (user `postgres`,
db `safepayai`) already running on localhost:5432 -- not Neon, per spec.md sec 12's own
"or a local docker Postgres" option for exactly this kind of test.

IMPORTANT: env vars for the app (PS_AUDIT_DATABASE_URL, PS_AUDIT_TRUSTED_ISSUERS, ...)
are set at MODULE level (not inside a fixture) because `app.main` builds its FastAPI
`app` object at import time and `app.settings.get_settings()` is `lru_cache`d -- both
must see the right environment before any test module does `from app.main import app`.
conftest.py is imported by pytest before sibling test modules, so this ordering holds.
"""

from __future__ import annotations

import os

from tests.integration._tokens import TEST_AUDIENCE, TEST_ISSUER, TEST_KID, TEST_SECRET

SUPERUSER_SYNC_URL = "postgresql://postgres:postgres@localhost:5432/safepayai"
SUPERUSER_ASYNC_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/safepayai"
APP_ROLE_PASSWORD = "audit_app_test_only_pw"
APP_ASYNC_URL = f"postgresql+asyncpg://audit_app:{APP_ROLE_PASSWORD}@localhost:5432/safepayai"

os.environ["PS_AUDIT_DATABASE_URL"] = APP_ASYNC_URL
os.environ.pop("PS_AUDIT_MIGRATE_DATABASE_URL", None)  # must never be set at app runtime
os.environ["PS_AUDIT_CHAIN_ID"] = "ps-demo-1"  # matches migration's genesis chain_id
os.environ["PS_AUDIT_ENV"] = "ci"
os.environ["PS_AUDIT_TRUSTED_ISSUERS"] = (
    f'{{"{TEST_ISSUER}": {{"{TEST_KID}": {{"public_key": "{TEST_SECRET}", "alg": "HS256"}}}}}}'
)
os.environ["PS_AUDIT_INTERNAL_AUDIENCE"] = TEST_AUDIENCE
os.environ["PS_AUDIT_APPEND_MAX_RETRIES"] = "3"
os.environ["PS_AUDIT_VERIFY_CHUNK"] = "500"
os.environ["PS_AUDIT_PAGE_MAX"] = "100"

import asyncio  # noqa: E402

import asyncpg  # noqa: E402
import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from alembic.config import Config  # noqa: E402

_SERVICE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _run_migration_fresh() -> None:
    """Drops the audit schema and re-runs the baseline migration as the bootstrap
    superuser (standing in for Neon's console-managed, login-capable owner credential
    per spec.md sec 8 -- audit_owner itself is NOLOGIN by design). Then sets a test-only
    password on audit_app so this test process can log in as the runtime role over TCP.
    """
    env = os.environ.copy()
    env["PS_AUDIT_MIGRATE_DATABASE_URL"] = SUPERUSER_ASYNC_URL

    async def _drop_schema() -> None:
        conn = await asyncpg.connect(SUPERUSER_SYNC_URL.replace("postgresql://", "postgresql://"))
        try:
            await conn.execute("DROP SCHEMA IF EXISTS audit CASCADE")
        finally:
            await conn.close()

    asyncio.run(_drop_schema())

    cfg = Config(os.path.join(_SERVICE_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_SERVICE_DIR, "migrations"))

    # Run in a subprocess so Alembic's own get_settings() (a *different* process) reads
    # PS_AUDIT_MIGRATE_DATABASE_URL fresh, never touching this test process's env/caches.
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=_SERVICE_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"alembic upgrade failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )

    async def _set_password() -> None:
        conn = await asyncpg.connect(SUPERUSER_SYNC_URL)
        try:
            await conn.execute(f"ALTER ROLE audit_app WITH PASSWORD '{APP_ROLE_PASSWORD}' LOGIN")
        finally:
            await conn.close()

    asyncio.run(_set_password())


@pytest.fixture(scope="session", autouse=True)
def _migrated_schema():
    """Session-scoped: migrate once. Test files are named test_a_*.py .. test_e_*.py so
    the ONE test that deliberately corrupts the chain (tamper detection) runs last,
    after every test that needs an internally-consistent chain (test-plan.md sec 4's
    "never on the live chain" intent, adapted here to "never before the tests that need
    the chain intact")."""
    _run_migration_fresh()
    yield


@pytest_asyncio.fixture
async def client():
    """httpx client against the real FastAPI app, in-process (ASGI transport).

    The engine (app.db's module-global singleton) is intentionally NOT disposed between
    tests: with a session-scoped event loop (pyproject.toml asyncio_default_*_loop_scope)
    every test in this session shares one loop, so the pooled asyncpg connections stay
    valid across tests and disposing/recreating the engine per test only adds overhead.
    """
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def owner_conn():
    """Raw asyncpg connection as the bootstrap superuser (stands in for a privileged
    attacker / migration owner in the tamper-demo scenario, spec.md sec 12)."""
    conn = await asyncpg.connect(SUPERUSER_SYNC_URL)
    try:
        yield conn
    finally:
        await conn.close()


@pytest_asyncio.fixture
async def app_role_conn():
    """Raw asyncpg connection AS the runtime role `audit_app` (not via the app's pooled
    SQLAlchemy engine) -- used to assert grant-level denial independent of app code."""
    conn = await asyncpg.connect(
        SUPERUSER_SYNC_URL.replace("postgres:postgres@", f"audit_app:{APP_ROLE_PASSWORD}@")
    )
    try:
        yield conn
    finally:
        await conn.close()
