"""Alembic environment for api-gateway.

version_table_schema="gateway" per docs/service-skeleton-conventions.md section 9.
Runs as mig_apigateway over the direct (migration) URL; refuses DDL on any other
schema.
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

SCHEMA = "gateway"

target_metadata = None  # Wave 4: DDL is hand-written in versions/; no ORM metadata yet.


def get_url() -> str:
    url = os.environ.get("PS_APIGATEWAY_MIGRATION_DATABASE_URL") or os.environ.get(
        "PS_APIGATEWAY_DATABASE_URL"
    )
    if not url:
        raise RuntimeError(
            "PS_APIGATEWAY_MIGRATION_DATABASE_URL (or PS_APIGATEWAY_DATABASE_URL) is not set"
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
    # alembic creates its own version table in `version_table_schema` before the
    # first migration runs; with a fresh database that schema doesn't exist yet
    # (the baseline revision is what creates it). Pre-create it here so the
    # chicken-and-egg ordering doesn't fail `alembic upgrade head` on an empty DB
    # (hit while wiring up Wave 5 integration tests against a throwaway Postgres).
    from sqlalchemy import text

    connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
    # Commit this standalone DDL statement now. Without this, the connection's
    # autobegin transaction stays open when `context.begin_transaction()` runs
    # next; Alembic sees a transaction already in progress and doesn't own/commit
    # it, so on `async with connectable.connect()` exit the whole migration
    # (schema + every table) is silently rolled back despite logging success.
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
