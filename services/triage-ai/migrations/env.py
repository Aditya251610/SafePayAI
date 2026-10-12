"""Alembic environment for triage-ai. version_table_schema="triage". Target metadata only
for the `triage` schema; refuses DDL elsewhere. No grant on any money-table schema
(mandate/checkout/resolution/paypal/...) per ADR-004/ADR-010.

Bug fix (same root cause independently found/fixed in catalog/api-gateway/audit/mandate,
see CLAUDE.md "known recurring failure classes"): with `version_table_schema` set, Alembic
creates `alembic_version` in that schema BEFORE the first migration runs (which is what
actually creates the schema), so a brand-new database fails with "schema triage does not
exist" before anything runs - and because that failure is inside a nested SAVEPOINT, it can
roll back silently with no visible error. Fix: pre-create the schema here, idempotently, and
explicitly `connection.commit()` it in its own transaction BEFORE Alembic's own transaction
begins (0001_baseline's own `CREATE SCHEMA IF NOT EXISTS` is then a no-op on top of this).
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

SCHEMA = "triage"

target_metadata = None  # DDL is hand-written in versions/; no ORM metadata.


def get_url() -> str:
    # Per CLAUDE.md "known recurring failure classes": every service reads
    # PS_<SLUG>_{DATABASE_URL,MIGRATION_DATABASE_URL} - never a bare DATABASE_URL.
    url = os.environ.get("PS_TRIAGEAI_MIGRATION_DATABASE_URL") or os.environ.get(
        "PS_TRIAGEAI_DATABASE_URL"
    )
    if not url:
        raise RuntimeError(
            "PS_TRIAGEAI_MIGRATION_DATABASE_URL (or PS_TRIAGEAI_DATABASE_URL) is not set"
        )
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        version_table_schema=SCHEMA,
        include_schemas=False,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
    connection.commit()
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table_schema=SCHEMA,
        include_schemas=False,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()
    connectable = async_engine_from_config(
        configuration, prefix="sqlalchemy.", poolclass=pool.NullPool
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
