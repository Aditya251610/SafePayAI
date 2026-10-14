"""checkout: add merchant_ids to orders, and backfill it from the parent cart.

`checkout.carts.merchant_ids` has existed since 0001_baseline, but `confirm_cart`
never copied it onto the order it creates, and `checkout.orders` never had the
column at all -- GET /orders had no way to scope a merchant-role caller to only
their own orders (found while wiring real per-merchant tenancy, gateway PR
feat/multi-tenant-merchant-identity). Backfill existing rows from their cart so
this isn't silently empty for orders created before this migration.

Revision ID: 0003_orders_merchant_ids
Revises: 0002_outbox_align_schema
Create Date: 2026-10-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_orders_merchant_ids"
down_revision: str | None = "0002_outbox_align_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "checkout"


def upgrade() -> None:
    jsonb = sa.dialects.postgresql.JSONB
    op.add_column(
        "orders",
        sa.Column("merchant_ids", jsonb, nullable=False, server_default="[]"),
        schema=SCHEMA,
    )
    op.execute(f"""
        UPDATE "{SCHEMA}"."orders" o
        SET merchant_ids = c.merchant_ids
        FROM "{SCHEMA}"."carts" c
        WHERE c.cart_id = o.cart_id
    """)


def downgrade() -> None:
    op.drop_column("orders", "merchant_ids", schema=SCHEMA)
