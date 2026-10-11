"""Alembic environment for paypal-adapter, schema `paypal` only.

version_table_schema="paypal" per docs/service-skeleton-conventions.md section 9.

Fixed (Wave 5B, same root cause independently found in mandate/catalog/api-gateway/audit,
CLAUDE.md "known recurring failure classes"): the migration URL is asyncpg
(postgresql+asyncpg://...), so this must drive Alembic through an async engine, not the
synchronous `engine_from_config` the Wave 4 stub used (that raised
`sqlalchemy.exc.MissingGreenlet` the moment it tried to connect). It also pre-creates the
`paypal` schema and commits that DDL in its own transaction before Alembic's own
transaction opens -- without the explicit commit, creating the schema inside the same
transaction as `version_table_schema="paypal"` silently rolls back on a fresh DB, because
Alembic tries to create `alembic_version` in that schema before 0001_baseline runs.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.settings import get_settings

SCHEMA = "paypal"

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()

target_metadata = None  # raw DDL via op.*, no ORM metadata in Wave 4/5


def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table" and getattr(object, "schema", None) not in (None, SCHEMA):
        return False
    return True


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
    connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
    connection.commit()  # see module docstring: must commit before Alembic's own transaction
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
