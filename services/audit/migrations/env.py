"""Alembic environment for the audit service.

version_table_schema="audit" (data-architecture.md sec 8: each service gets its own
alembic_version table scoped to its schema). include_schemas is left False and no
target_metadata is declared for any schema but audit's -- this service's baseline
revision uses raw op.* calls scoped to schema="audit" throughout, so there is nothing
else for Alembic to autogenerate against or accidentally touch in another schema.

Runs against PS_AUDIT_MIGRATE_DATABASE_URL (direct Neon endpoint, audit_owner/mig_audit
role) via app.settings -- never the pooled runtime URL (spec.md sec 8).
"""

from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

# Ensure `app` (services/audit/app) is importable regardless of the cwd Alembic is
# invoked from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.settings import get_settings  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None

SCHEMA = "audit"


def get_url() -> str:
    settings = get_settings()
    url = settings.migrate_database_url
    if not url:
        raise RuntimeError(
            "PS_AUDIT_MIGRATE_DATABASE_URL is required to run Alembic migrations "
            "(direct Neon endpoint, audit_owner/mig_audit role; never set at runtime)."
        )
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        version_table_schema=SCHEMA,
        include_schemas=False,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    # Bootstrap-only chicken-and-egg fix: Alembic's own version-table bookkeeping
    # (`_ensure_version_table`, scoped to `version_table_schema=SCHEMA`) runs BEFORE any
    # upgrade script executes, so on a brand-new database it tries to
    # `CREATE TABLE audit.alembic_version` before this revision's own `upgrade()` has
    # had a chance to `CREATE SCHEMA audit`. Create the (otherwise-empty) schema shell
    # here so Alembic's bookkeeping has somewhere to write; revision 0001 still owns all
    # real schema/role/grant/trigger DDL.
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
    connectable = create_async_engine(get_url(), poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
