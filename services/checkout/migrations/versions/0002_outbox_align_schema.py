"""checkout: align outbox schema with the other 6 producer services

0001_baseline's `outbox` table diverged from the canonical shape documented in
data-architecture.md section 7 (`seq, event_id, type, version, aggregate_id, payload,
trace_id, created_at, delivered_to jsonb, attempts, next_attempt_at`) -- it was missing
`version`, `trace_id`, `created_at`, and `next_attempt_at`, and used a scalar `delivered_at`
timestamp instead of the `delivered_to` jsonb map every other producer (mandate,
shopping-agent, paypal-adapter, tracking, resolution, triage-ai) uses. Found while building
the shared outbox-relay helper (libs/common/safepayai_common/outbox/relay.py, sprint-plan
S2-06) -- a single relay implementation needs one consistent column shape across all 7
producers' tables.

Safe additive/rename migration: nothing outside migrations/repo.py reads or writes
`delivered_at` yet (checkout's own `/internal/outbox/flush` was still a 501 stub before this
change), so there is no data to migrate off that column.

Revision ID: 0002_outbox_align_schema
Revises: 0001_baseline
Create Date: 2026-10-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_outbox_align_schema"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "checkout"


def upgrade() -> None:
    jsonb = sa.dialects.postgresql.JSONB
    op.add_column(
        "outbox",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        schema=SCHEMA,
    )
    op.add_column(
        "outbox",
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "outbox",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "outbox",
        sa.Column("delivered_to", jsonb, nullable=False, server_default="{}"),
        schema=SCHEMA,
    )
    op.add_column(
        "outbox",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.drop_column("outbox", "delivered_at", schema=SCHEMA)
    op.execute(
        f'CREATE INDEX IF NOT EXISTS idx_checkout_outbox_next_attempt ON "{SCHEMA}"."outbox"(next_attempt_at)'
    )


def downgrade() -> None:
    op.execute(f'DROP INDEX IF EXISTS "{SCHEMA}".idx_checkout_outbox_next_attempt')
    op.add_column(
        "outbox",
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.drop_column("outbox", "next_attempt_at", schema=SCHEMA)
    op.drop_column("outbox", "delivered_to", schema=SCHEMA)
    op.drop_column("outbox", "created_at", schema=SCHEMA)
    op.drop_column("outbox", "trace_id", schema=SCHEMA)
    op.drop_column("outbox", "version", schema=SCHEMA)
