"""Schema/role grant helper, called from each service's baseline Alembic migration.

Per architecture/data-architecture.md §4. No business logic — DDL only. Each service passes its
own schema name, migration-owner role, and runtime-role grant list; this module just emits the
SQL in a consistent, auditable shape so the CI grants-matrix test can assert against it.
"""

from __future__ import annotations

from dataclasses import dataclass
from sqlalchemy import text
from sqlalchemy.engine import Connection

ROLE_FLAGS = "NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS LOGIN"


@dataclass(frozen=True)
class TableGrant:
    table: str
    privileges: tuple[str, ...]  # e.g. ("SELECT", "INSERT")


def create_schema_and_roles(conn: Connection, schema: str, migration_role: str, runtime_role: str) -> None:
    conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    conn.execute(text(f"REVOKE ALL ON SCHEMA \"{schema}\" FROM PUBLIC"))
    conn.execute(text(f'GRANT USAGE ON SCHEMA "{schema}" TO "{runtime_role}"'))


def apply_table_grants(conn: Connection, schema: str, runtime_role: str, grants: list[TableGrant]) -> None:
    for g in grants:
        privs = ", ".join(g.privileges)
        conn.execute(text(f'GRANT {privs} ON "{schema}"."{g.table}" TO "{runtime_role}"'))


def deny_cross_schema(conn: Connection, runtime_role: str, other_schemas: list[str]) -> None:
    """No-op by default (deny is the absence of a grant). Kept as an explicit assertion point for
    the CI grants-matrix test (has_schema_privilege must be false for every entry here)."""
    return None
