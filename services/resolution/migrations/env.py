"""Alembic env for resolution. version_table_schema="resolution" (data-architecture.md
section 3). Target metadata only for the `resolution` schema; refuses DDL elsewhere."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.settings import settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

SCHEMA = "resolution"
target_metadata = None


def get_url() -> str:
    return settings.database_url


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


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        connection.execute(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"')
        connection.execute(f'CREATE TABLE IF NOT EXISTS "{SCHEMA}".alembic_version (version_num varchar(32) NOT NULL)')
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=SCHEMA,
            include_schemas=False,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
