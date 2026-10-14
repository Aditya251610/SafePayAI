"""checkout: add item_titles to orders, backfilled from the parent cart's lines.

triage-ai's OrderFacts.item_titles input was always empty -- catalog's own
PricedLine never carried a title (even though the seed data has one and the
query already selects it), so there was nothing to copy through. Catalog now
returns title on every priced line; this stores it on the order the same way
merchant_ids already is (0003), so resolution's decide.py can read it back via
GET /orders/{id} for triage-ai's real input instead of always sending [].

Revision ID: 0006_orders_item_titles
Revises: 0005_orders_buyer_id_index
Create Date: 2026-10-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_orders_item_titles"
down_revision: str | None = "0005_orders_buyer_id_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "checkout"


def upgrade() -> None:
    jsonb = sa.dialects.postgresql.JSONB
    op.add_column(
        "orders",
        sa.Column("item_titles", jsonb, nullable=False, server_default="[]"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("orders", "item_titles", schema=SCHEMA)
