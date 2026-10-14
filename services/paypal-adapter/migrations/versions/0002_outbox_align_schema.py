"""paypal-adapter: align outbox schema with the other 6 producer services

0001_baseline's `outbox` table diverged from the canonical shape documented in
data-architecture.md section 7 (`seq, event_id, type, version, aggregate_id, payload,
trace_id, created_at, delivered_to jsonb, attempts, next_attempt_at`) -- it was missing
`version` and `next_attempt_at`, and used a scalar `delivered_at` timestamp instead of the
`delivered_to` jsonb map every other producer uses. The shared outbox-relay helper
(libs/common/safepayai_common/outbox/relay.py, sprint-plan S2-06) hard-codes a SELECT
against the canonical column list, so `POST /internal/outbox/flush` (mounted in
app/routers/internal.py) would fail with a column-does-not-exist error on its first real
call -- `paypal.call_recorded`/similar events would never reach audit. Found via a
backend-completeness review; checkout hit the identical divergence and was fixed the same
way in its own 0002_outbox_align_schema migration.

Safe additive/rename migration: nothing reads or writes `delivered_at` yet (this service's
`/internal/outbox/flush` was never successfully exercised against a real row before this
fix -- `tests/integration/test_outbox_flush.py` only covered the unreachable-audit path,
never a flush test), so there is no data to migrate off that column.

Revision ID: 0002_outbox_align_schema
Revises: 0001_baseline
Create Date: 2026-10-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_outbox_align_schema"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "paypal"


def upgrade() -> None:
    jsonb = sa.dialects.postgresql.JSONB
    op.add_column(
        "outbox",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
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
        f"CREATE INDEX IF NOT EXISTS idx_paypal_outbox_next_attempt "
        f'ON "{SCHEMA}"."outbox"(next_attempt_at)'
    )


def downgrade() -> None:
    op.execute(f'DROP INDEX IF EXISTS "{SCHEMA}".idx_paypal_outbox_next_attempt')
    op.add_column(
        "outbox",
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.drop_column("outbox", "next_attempt_at", schema=SCHEMA)
    op.drop_column("outbox", "delivered_to", schema=SCHEMA)
    op.drop_column("outbox", "version", schema=SCHEMA)
