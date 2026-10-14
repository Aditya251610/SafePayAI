"""api-gateway: add merchant_id to users for real per-merchant tenancy.

The merchant login was a single shared demo account (spec.md section 3 /
GW-S1-04/05) with no binding to a specific catalog merchant_id -- "merchant"
was a role flag only, not an identity. This adds a nullable merchant_id column
so a merchant-role user can be scoped to exactly one of catalog's seeded
merchant ids (mrc_trailhead/mrc_hearth/mrc_pixelwire), threaded through the
internal JWT's merchant_id claim (tokens/mint.py) so checkout can filter
GET /orders to only that merchant's orders. NULL for non-merchant roles and
for any merchant user not yet migrated to a specific storefront.

Revision ID: 0002_merchant_identity
Revises: 0001_baseline
Create Date: 2026-10-15
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_merchant_identity"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "gateway"


def upgrade() -> None:
    op.execute(f'ALTER TABLE "{SCHEMA}"."users" ADD COLUMN merchant_id text')


def downgrade() -> None:
    op.execute(f'ALTER TABLE "{SCHEMA}"."users" DROP COLUMN merchant_id')
