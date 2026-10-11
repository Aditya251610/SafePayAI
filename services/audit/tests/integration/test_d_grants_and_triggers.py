"""Append-only enforcement (test-plan.md sec 1): direct UPDATE/DELETE/TRUNCATE as the
runtime role `audit_app` must be denied at the DB level (grants + trigger), independent
of the app. Also asserts `audit_app` cannot disable the trigger (no TRIGGER privilege,
not the table owner).
"""

from __future__ import annotations

import asyncpg
import pytest

pytestmark = pytest.mark.asyncio


async def test_app_role_cannot_update(app_role_conn: asyncpg.Connection) -> None:
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_role_conn.execute("UPDATE audit.entries SET payload = '{}' WHERE seq = 1")


async def test_app_role_cannot_delete(app_role_conn: asyncpg.Connection) -> None:
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_role_conn.execute("DELETE FROM audit.entries WHERE seq = 1")


async def test_app_role_cannot_truncate(app_role_conn: asyncpg.Connection) -> None:
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_role_conn.execute("TRUNCATE audit.entries")


async def test_app_role_cannot_disable_trigger(app_role_conn: asyncpg.Connection) -> None:
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_role_conn.execute("ALTER TABLE audit.entries DISABLE TRIGGER USER")


async def test_owner_update_blocked_by_trigger_even_with_grants(
    owner_conn: asyncpg.Connection,
) -> None:
    """The bootstrap superuser has full grants (defense-in-depth layer 1 bypassed), but
    the BEFORE UPDATE trigger (layer 2) still raises -- proving the trigger fires even
    for an elevated role, not just one that lacks grants (test-plan.md sec 1 case 4)."""
    with pytest.raises(asyncpg.InsufficientPrivilegeError, match="audit_is_append_only"):
        await owner_conn.execute("UPDATE audit.entries SET payload = '{}' WHERE seq = 1")


async def test_owner_delete_blocked_by_trigger(owner_conn: asyncpg.Connection) -> None:
    with pytest.raises(asyncpg.InsufficientPrivilegeError, match="audit_is_append_only"):
        await owner_conn.execute("DELETE FROM audit.entries WHERE seq = 1")


async def test_owner_truncate_blocked_by_trigger(owner_conn: asyncpg.Connection) -> None:
    with pytest.raises(asyncpg.InsufficientPrivilegeError, match="audit_is_append_only"):
        await owner_conn.execute("TRUNCATE audit.entries")


async def test_app_role_has_only_insert_select(app_role_conn: asyncpg.Connection) -> None:
    rows = await app_role_conn.fetch(
        """
        SELECT table_name, privilege_type FROM information_schema.role_table_grants
        WHERE grantee = 'audit_app' AND table_schema = 'audit'
        ORDER BY table_name, privilege_type
        """
    )
    grants = {(r["table_name"], r["privilege_type"]) for r in rows}
    allowed_privs = {"INSERT", "SELECT"}
    for table_name, priv in grants:
        assert priv in allowed_privs, f"unexpected privilege {priv} on {table_name}"
    tables_with_grants = {t for t, _ in grants}
    assert tables_with_grants == {"entries", "verify_runs", "head_exports"}
