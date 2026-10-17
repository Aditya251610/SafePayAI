"""catalog: public categories view + dev/CI login passwords for bootstrap roles.

Two fixes needed for Wave 5 (real DB reads) that 0001_baseline didn't cover:

1. `GET /categories` (api.md) needs a public view. 0001_baseline granted the runtime
   role SELECT on `v_items_public`, `v_prices_public`, `v_merchants_public`,
   `catalog_versions`, `merchant_refund_policy_seeds` (spec.md section 1) but never
   created a categories view or granted the bare `categories` table - the categories
   table has no untrusted/fixture columns to hide, but the "runtime role only touches
   views + the two named reference tables" shape from spec.md section 1 is kept
   consistent by adding `v_categories_public` rather than granting the base table.

2. 0001_baseline's idempotent role bootstrap (its own docstring: "convenience for
   `alembic upgrade head` on an empty database") creates `mig_catalog`/`svc_catalog`
   with `LOGIN` but never sets a password, so nothing can actually authenticate as
   them - a gap, not by design. This sets the same placeholder password already
   committed in `.env.example` (`changeme`), overridable via
   `PS_CATALOG_DEV_DB_PASSWORD` for local/CI only. Production provisioning sets a real
   password out of band (ops tooling), same as 0001_baseline's own role-creation
   caveat already states.

Revision ID: 0003_categories_view
Revises: 0002_seed_v1
Create Date: 2026-10-11

Note: the alembic_version table is `version_num varchar(32)` (Alembic's own default),
so the revision id below is kept <= 32 chars - this filename is longer than its
revision id on purpose.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from safepayai_common.db.grants import TableGrant, apply_table_grants

revision: str = "0003_categories_view"
down_revision: str | None = "0002_seed_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "catalog"
RUNTIME_ROLE = "svc_catalog"
MIGRATION_ROLE = "mig_catalog"


def upgrade() -> None:
    bind = op.get_bind()

    op.execute(
        f'''
        CREATE VIEW "{SCHEMA}"."v_categories_public" AS
        SELECT category_id, display_name FROM "{SCHEMA}"."categories"
        '''
    )
    apply_table_grants(
        bind, SCHEMA, RUNTIME_ROLE, [TableGrant("v_categories_public", ("SELECT",))]
    )

    # This block only applies locally/in CI, where migrations run as docker-compose's
    # `postgres` superuser. Production's mig_catalog is deliberately NOCREATEROLE (the
    # role-flag set data-architecture.md requires for every mig_<slug> role), and
    # Postgres requires CREATEROLE (not just ADMIN OPTION) to ALTER another role's
    # password - so a NOCREATEROLE mig_catalog can never run this statement, which is
    # correct: production's real passwords are set out of band by ops tooling before
    # this migration ever runs, per this file's own docstring above. Previously this
    # unconditionally attempted the ALTER ROLE and crashed the whole migration (plus
    # the earlier 0001/0002 DDL in the same transaction, since transaction_per_migration
    # isn't set) the first time it ran anywhere but a local/CI superuser connection.
    can_alter_roles = bind.execute(
        sa.text("SELECT rolcreaterole FROM pg_roles WHERE rolname = current_user")
    ).scalar()
    if can_alter_roles:
        # ALTER ROLE ... PASSWORD does not accept a bind parameter (Postgres does not
        # allow a protocol parameter in that value position); escape the single
        # placeholder dev/CI password value instead of interpolating caller input.
        dev_password = os.environ.get("PS_CATALOG_DEV_DB_PASSWORD", "changeme").replace(
            "'", "''"
        )
        for role in (MIGRATION_ROLE, RUNTIME_ROLE):
            bind.execute(sa.text(f"ALTER ROLE \"{role}\" WITH PASSWORD '{dev_password}'"))


def downgrade() -> None:
    op.execute(f'DROP VIEW IF EXISTS "{SCHEMA}"."v_categories_public"')
