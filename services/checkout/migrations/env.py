"""Alembic environment for checkout, schema `checkout` only.

version_table_schema="checkout" per docs/service-skeleton-conventions.md section 9.

Bug fix (Wave 5B, same class as catalog/mandate hit independently - CLAUDE.md "known
recurring failure classes"): the DB URL is asyncpg (`postgresql+asyncpg://`), so this
must use an async engine, not `engine_from_config`/`connectable.connect()` (sync). Also
pre-creates the `checkout` schema and commits it in its own transaction before Alembic's
`begin_transaction()` - without that, on a brand-new database, Alembic creates
`alembic_version` in the (not-yet-existing) `checkout` schema and fails outright, and
even if it didn't, a connection close at the end of a migration run with nothing to do
would otherwise roll the implicit outer transaction (schema included) back.
"""

from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.settings import get_settings

SCHEMA = "checkout"

config = context.config

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.migration_db_url)

target_metadata = None  # raw DDL via op.*, no ORM metadata in Wave 4


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
