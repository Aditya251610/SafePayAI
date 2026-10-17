"""Alembic environment for resolution, schema `resolution` only.

version_table_schema="resolution" per docs/service-skeleton-conventions.md section 9.

Bug fix (Wave 5B, CLAUDE.md "known recurring failure classes" - Alembic schema-bootstrap
race): same class of bug independently hit and fixed in several other services this session
- the DB URL is asyncpg, so this must use an async engine, not `engine_from_config` (sync, and
passes a raw string instead of `text()` to `Connection.execute`, which SQLAlchemy 2 rejects).
Also pre-creates the `resolution` schema and commits it in its own transaction before
Alembic's `begin_transaction()`, mirroring services/checkout/migrations/env.py.
"""

from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app_resolution.settings import settings

SCHEMA = "resolution"

config = context.config
config.set_main_option(
    "sqlalchemy.url", settings.migration_database_url or settings.database_url
)

target_metadata = None


def include_object(object, name, type_, reflected, compare_to):
    return not (
        type_ == "table" and getattr(object, "schema", None) not in (None, SCHEMA)
    )


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        version_table_schema=SCHEMA,
        include_schemas=False,
        include_object=include_object,
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
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
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
