"""checkout: add mandate_reservation_id to orders.

confirm_cart now creates a real reservation on mandate's own reservation state
machine (mandate/app/routers/reservations.py) alongside the existing
committed_minor cap check -- this column remembers which reservation backs
each order so the capture flow can authorize-capture/commit/release it later.

Revision ID: 0004_orders_mandate_reservation_id
Revises: 0003_orders_merchant_ids
Create Date: 2026-10-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_mandate_reservation_id"
down_revision: str | None = "0003_orders_merchant_ids"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "checkout"


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("mandate_reservation_id", sa.String(length=64), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("orders", "mandate_reservation_id", schema=SCHEMA)
