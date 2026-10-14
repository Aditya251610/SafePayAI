"""checkout: index orders.buyer_id for the new buyer-scoped (no mandate_id) list.

GET /orders now supports listing a buyer's orders across every mandate
(bff/buyer-home, spec.md C9) instead of requiring mandate_id -- needs its own
index, mirroring ix_checkout_orders_mandate_id from 0001_baseline.

Revision ID: 0005_orders_buyer_id_index
Revises: 0004_mandate_reservation_id
Create Date: 2026-10-15
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005_orders_buyer_id_index"
down_revision: str | None = "0004_mandate_reservation_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "checkout"


def upgrade() -> None:
    op.create_index(
        "ix_checkout_orders_buyer_id", "orders", ["buyer_id"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_checkout_orders_buyer_id", table_name="orders", schema=SCHEMA)
