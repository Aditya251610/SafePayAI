"""Alembic environment for shopping-agent, schema `agent` only.

version_table_schema="agent" per docs/service-skeleton-conventions.md section 9. Refuses DDL
on any other schema: target_metadata only contains this service's own tables. Runs as an
async engine (direct asyncpg DSN) -- a sync engine against an asyncpg URL raises
sqlalchemy.exc.MissingGreenlet, the same failure class already fixed in catalog/mandate/
api-gateway/audit/paypal-adapter's env.py (see CLAUDE.md "known recurring failure classes").
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app_shopping_agent.settings import get_settings

SCHEMA = "agent"

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()

target_metadata = None  # raw DDL via op.*, no ORM metadata in Wave 4


def include_object(object, name, type_, reflected, compare_to):
    return not (
        type_ == "table" and getattr(object, "schema", None) not in (None, SCHEMA)
    )


def run_migrations_offline() -> None:
    context.configure(
        url=settings.migration_db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        version_table_schema=SCHEMA,
        include_schemas=False,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    # Pre-create the schema and commit before Alembic's own transaction begins --
    # otherwise, with version_table_schema set, Alembic tries to create
    # alembic_version in a schema that doesn't exist yet (see module docstring).
    connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
    connection.commit()
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table_schema=SCHEMA,
        include_schemas=False,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = settings.migration_db_url
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
