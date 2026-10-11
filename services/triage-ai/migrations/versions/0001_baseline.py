"""baseline: triage schema, tables, grants

Revision ID: 0001
Revises:
Create Date: 2026-10-11

Tables per data-architecture.md section 3 (triage row: `triage_log`) and triage-ai/spec.md
section 10 + conflict #5 (adds `triage.outbox`, required by ADR-003 for an event producer;
service-map owner acknowledgement requested, not yet merged there). Grants via libs/common's
safepayai_common.db.grants helper; runtime role gets NO grant on any other schema
(mandate/checkout/resolution/paypal/...) per ADR-004/ADR-010.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from safepayai_common.db.grants import TableGrant, apply_table_grants, create_schema_and_roles

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "triage"
MIGRATION_ROLE = "mig_triage"
RUNTIME_ROLE = "svc_triage"


def upgrade() -> None:
    bind = op.get_bind()
    create_schema_and_roles(bind, SCHEMA, MIGRATION_ROLE, RUNTIME_ROLE)

    op.create_table(
        "triage_log",
        sa.Column("triage_id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", sa.Text(), nullable=False),
        sa.Column("trace_id", sa.Text(), nullable=True),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("input_sha256", sa.Text(), nullable=True),
        sa.Column("output_sha256", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("route", sa.Text(), nullable=True),
        sa.Column("reasons", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("flags", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("gate_hits", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_triage_log_case_task_input_prompt",
        "triage_log",
        ["case_id", "task", "input_sha256", "prompt_version"],
        schema=SCHEMA,
    )

    op.create_table(
        "outbox",
        sa.Column("seq", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("aggregate_id", sa.Text(), nullable=False),
        sa.Column("payload", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("trace_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("delivered_to", sa.dialects.postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )

    apply_table_grants(
        bind,
        SCHEMA,
        RUNTIME_ROLE,
        [
            TableGrant("triage_log", ("SELECT", "INSERT")),
            TableGrant("outbox", ("SELECT", "INSERT", "UPDATE", "DELETE")),
        ],
    )


def downgrade() -> None:
    op.drop_table("outbox", schema=SCHEMA)
    op.drop_table("triage_log", schema=SCHEMA)
