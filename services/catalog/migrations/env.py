"""Alembic environment for catalog.

version_table_schema="catalog" per docs/service-skeleton-conventions.md section 9 /
data-architecture.md section 8 so this service has its own alembic_version row inside
its own schema. Runs as mig_catalog over the direct (migration) URL; refuses DDL on
any other schema (no target metadata for foreign schemas; no `include_schemas` scan).
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

SCHEMA = "catalog"

target_metadata = None  # Wave 4: DDL is hand-written in versions/; no ORM metadata yet.


def get_url() -> str:
    url = os.environ.get("PS_CATALOG_MIGRATION_DATABASE_URL") or os.environ.get(
        "PS_CATALOG_DATABASE_URL"
    )
    if not url:
        raise RuntimeError(
            "PS_CATALOG_MIGRATION_DATABASE_URL (or PS_CATALOG_DATABASE_URL) is not set"
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
    # Bug fix (Wave 5): with version_table_schema set, Alembic creates the
    # alembic_version table in that schema BEFORE running 0001_baseline (which is what
    # actually creates the "catalog" schema), so a brand-new database fails with
    # "schema catalog does not exist" before a single migration runs. Pre-create the
    # schema here, idempotently; 0001_baseline's own `CREATE SCHEMA IF NOT EXISTS` is
    # then a no-op on top of this.
    connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
    # Commit this pre-flight DDL in its own transaction. SQLAlchemy 2.0 connections
    # open a transaction implicitly on first execute; without an explicit commit here,
    # Alembic's own `begin_transaction()` below nests inside it (as a SAVEPOINT) and,
    # on a database with nothing to migrate from a prior run, the connection close at
    # the end of `run_migrations_online` rolls everything - schema included - back.
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
