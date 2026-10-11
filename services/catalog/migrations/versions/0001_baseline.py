"""catalog baseline: schema, tables, views, grants

Tables/columns from .claude/prd/architecture/data-architecture.md section 3 and
.claude/prd/services/catalog/spec.md section 1. Grants via libs/common's
safepayai_common.db.grants helper per docs/service-skeleton-conventions.md section 9.

Role naming note (flagged conflict): catalog/spec.md section 1 names its own roles
`catalog_ro` (runtime) / `catalog_seed` (write/admin). The binding conventions doc
(section 9) and data-architecture.md section 4 use the generic `mig_<slug>` /
`svc_<slug>` scheme (`mig_catalog` / `svc_catalog`) shared by every service's grants
helper call. Per the conventions doc's own tie-break rule ("if a service's spec.md
conflicts with this doc on something not listed as service-specific, this doc wins"),
this migration uses `mig_catalog` / `svc_catalog`. Flagged for the catalog owner.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-11
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from safepayai_common.db.grants import TableGrant, apply_table_grants, create_schema_and_roles

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "catalog"
MIGRATION_ROLE = "mig_catalog"
RUNTIME_ROLE = "svc_catalog"


def upgrade() -> None:
    bind = op.get_bind()

    # Idempotent local/CI role bootstrap (data-architecture.md section 1: "CREATE ROLE
    # via SQL works"). Production roles are expected to be provisioned by ops tooling;
    # this is a convenience for `alembic upgrade head` on an empty database.
    for role in (MIGRATION_ROLE, RUNTIME_ROLE):
        bind.execute(
            sa.text(
                f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                        CREATE ROLE "{role}" NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS LOGIN;
                    END IF;
                END $$;
                """
            )
        )

    create_schema_and_roles(bind, SCHEMA, MIGRATION_ROLE, RUNTIME_ROLE)

    op.execute(f'''
        CREATE TABLE "{SCHEMA}"."catalog_versions" (
            version integer PRIMARY KEY,
            seed_hash text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            reason text
        )
    ''')

    op.execute(f'''
        CREATE TABLE "{SCHEMA}"."merchants" (
            merchant_id text PRIMARY KEY,
            display_name text NOT NULL,
            description text,
            active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    ''')

    op.execute(f'''
        CREATE TABLE "{SCHEMA}"."merchant_settlement_map" (
            merchant_id text NOT NULL REFERENCES "{SCHEMA}"."merchants"(merchant_id),
            settlement_alias text NOT NULL,
            currency char(3) NOT NULL CHECK (currency ~ '^[A-Z]{{3}}$'),
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (merchant_id)
        )
    ''')

    op.execute(f'''
        CREATE TABLE "{SCHEMA}"."categories" (
            category_id text PRIMARY KEY,
            display_name text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    ''')

    op.execute(f'''
        CREATE TABLE "{SCHEMA}"."items" (
            sku text PRIMARY KEY,
            merchant_id text NOT NULL REFERENCES "{SCHEMA}"."merchants"(merchant_id),
            category_id text NOT NULL REFERENCES "{SCHEMA}"."categories"(category_id),
            title text NOT NULL,
            description text NOT NULL,
            active boolean NOT NULL DEFAULT true,
            created_in_version integer NOT NULL REFERENCES "{SCHEMA}"."catalog_versions"(version),
            created_at timestamptz NOT NULL DEFAULT now()
        )
    ''')

    op.execute(f'''
        CREATE TABLE "{SCHEMA}"."item_prices" (
            sku text NOT NULL REFERENCES "{SCHEMA}"."items"(sku),
            catalog_version integer NOT NULL REFERENCES "{SCHEMA}"."catalog_versions"(version),
            unit_price_minor bigint NOT NULL CHECK (unit_price_minor > 0),
            currency char(3) NOT NULL CHECK (currency = 'USD'),
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (sku, catalog_version)
        )
    ''')

    op.execute(f'''
        CREATE TABLE "{SCHEMA}"."merchant_refund_policy_seeds" (
            merchant_id text NOT NULL REFERENCES "{SCHEMA}"."merchants"(merchant_id),
            refund_cap_minor bigint NOT NULL,
            excluded_category_ids text[] NOT NULL DEFAULT '{{}}',
            velocity_max_refunds integer NOT NULL,
            velocity_window_days integer NOT NULL,
            note text,
            PRIMARY KEY (merchant_id)
        )
    ''')

    op.execute(f'''
        CREATE TABLE "{SCHEMA}"."item_fixtures" (
            sku text PRIMARY KEY REFERENCES "{SCHEMA}"."items"(sku),
            kind text NOT NULL,
            expected_behavior text NOT NULL,
            target_sku text
        )
    ''')

    op.execute(f'''
        CREATE INDEX IF NOT EXISTS idx_items_merchant ON "{SCHEMA}"."items"(merchant_id)
    ''')
    op.execute(f'''
        CREATE INDEX IF NOT EXISTS idx_items_category ON "{SCHEMA}"."items"(category_id)
    ''')

    # Public views (no item_fixtures join) per spec.md section 1.
    op.execute(f'''
        CREATE VIEW "{SCHEMA}"."v_merchants_public" AS
        SELECT m.merchant_id, m.display_name, sm.settlement_alias, sm.currency
        FROM "{SCHEMA}"."merchants" m
        JOIN "{SCHEMA}"."merchant_settlement_map" sm ON sm.merchant_id = m.merchant_id
        WHERE m.active
    ''')

    op.execute(f'''
        CREATE VIEW "{SCHEMA}"."v_items_public" AS
        SELECT i.sku, i.merchant_id, i.category_id, i.title, i.description, i.active,
               i.created_in_version
        FROM "{SCHEMA}"."items" i
    ''')

    op.execute(f'''
        CREATE VIEW "{SCHEMA}"."v_prices_public" AS
        SELECT sku, catalog_version, unit_price_minor, currency
        FROM "{SCHEMA}"."item_prices"
    ''')

    grants = [
        TableGrant("v_items_public", ("SELECT",)),
        TableGrant("v_prices_public", ("SELECT",)),
        TableGrant("v_merchants_public", ("SELECT",)),
        TableGrant("catalog_versions", ("SELECT",)),
        TableGrant("merchant_refund_policy_seeds", ("SELECT",)),
    ]
    apply_table_grants(bind, SCHEMA, RUNTIME_ROLE, grants)


def downgrade() -> None:
    bind = op.get_bind()
    op.execute(f'DROP VIEW IF EXISTS "{SCHEMA}"."v_prices_public"')
    op.execute(f'DROP VIEW IF EXISTS "{SCHEMA}"."v_items_public"')
    op.execute(f'DROP VIEW IF EXISTS "{SCHEMA}"."v_merchants_public"')
    op.execute(f'DROP TABLE IF EXISTS "{SCHEMA}"."item_fixtures"')
    op.execute(f'DROP TABLE IF EXISTS "{SCHEMA}"."merchant_refund_policy_seeds"')
    op.execute(f'DROP TABLE IF EXISTS "{SCHEMA}"."item_prices"')
    op.execute(f'DROP TABLE IF EXISTS "{SCHEMA}"."items"')
    op.execute(f'DROP TABLE IF EXISTS "{SCHEMA}"."categories"')
    op.execute(f'DROP TABLE IF EXISTS "{SCHEMA}"."merchant_settlement_map"')
    op.execute(f'DROP TABLE IF EXISTS "{SCHEMA}"."merchants"')
    op.execute(f'DROP TABLE IF EXISTS "{SCHEMA}"."catalog_versions"')
    op.execute(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE')
