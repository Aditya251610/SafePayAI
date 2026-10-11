"""Alembic environment for mandate.

version_table_schema="mandate" per docs/service-skeleton-conventions.md section 9.
Runs as mig_mandate over the direct (migration) URL; refuses DDL on any other schema.
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

SCHEMA = "mandate"

target_metadata = None  # Wave 4: DDL is hand-written in versions/; no ORM metadata yet.


def get_url() -> str:
    url = os.environ.get("PS_MANDATE_MIGRATION_DATABASE_URL") or os.environ.get(
        "PS_MANDATE_DATABASE_URL"
    )
    if not url:
        raise RuntimeError(
            "PS_MANDATE_MIGRATION_DATABASE_URL (or PS_MANDATE_DATABASE_URL) is not set"
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
    # Bug fix (Wave 5, same root cause independently found in catalog/api-gateway/audit):
    # with version_table_schema set, Alembic creates the alembic_version table in that
    # schema BEFORE running 0001_baseline (which actually creates the "mandate" schema),
    # so a brand-new database fails with "schema mandate does not exist" before a single
    # migration runs - this was silently broken in CI the whole time (mandate/integration
    # has never actually passed there). Pre-create the schema here, idempotently;
    # 0001_baseline's own `CREATE SCHEMA IF NOT EXISTS` is then a no-op on top of this.
    connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
    # Commit this pre-flight DDL in its own transaction - see catalog/migrations/env.py's
    # identical comment for why (nested SAVEPOINT rollback on close otherwise).
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
