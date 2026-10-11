"""baseline: schema agent + proposal_log/outbox/idempotency_keys + grants

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-11

Creates schema `agent` (data-architecture.md section 3) and its Wave-4 tables, then grants
via safepayai_common.db.grants (mig_agent owns, svc_agent gets INSERT/SELECT/UPDATE per
data-architecture.md section 4; shopping-agent/spec.md section 12).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from safepayai_common.db.grants import (
    TableGrant,
    apply_table_grants,
    create_schema_and_roles,
)

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "agent"
MIGRATION_ROLE = "mig_agent"
RUNTIME_ROLE = "svc_agent"


def upgrade() -> None:
    op.execute(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"')

    op.create_table(
        "proposal_log",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "trace_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column(
            "mandate_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("input_sha256", sa.String(length=64), nullable=False),
        sa.Column("output_sha256", sa.String(length=64), nullable=True),
        sa.Column("output_json", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("validation_result", sa.String(length=32), nullable=True),
        sa.Column(
            "injection_suspected",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_agent_proposal_log_mandate_id",
        "proposal_log",
        ["mandate_id"],
        schema=SCHEMA,
    )

    op.create_table(
        "outbox",
        sa.Column("seq", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "event_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
            unique=True,
        ),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "aggregate_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("payload", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("trace_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "delivered_to",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("done", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_agent_outbox_pending",
        "outbox",
        ["next_attempt_at"],
        schema=SCHEMA,
        postgresql_where=sa.text("done = false"),
    )

    op.create_table(
        "idempotency_keys",
        sa.Column("scope", sa.String(length=64), primary_key=True),
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema=SCHEMA,
    )

    conn = op.get_bind()
    create_schema_and_roles(conn, SCHEMA, MIGRATION_ROLE, RUNTIME_ROLE)
    apply_table_grants(
        conn,
        SCHEMA,
        RUNTIME_ROLE,
        [
            TableGrant("proposal_log", ("INSERT", "SELECT")),
            TableGrant("outbox", ("INSERT", "SELECT", "UPDATE")),
            TableGrant("idempotency_keys", ("INSERT", "SELECT", "UPDATE")),
        ],
    )


def downgrade() -> None:
    op.drop_table("idempotency_keys", schema=SCHEMA)
    op.drop_index("ix_agent_outbox_pending", table_name="outbox", schema=SCHEMA)
    op.drop_table("outbox", schema=SCHEMA)
    op.drop_index(
        "ix_agent_proposal_log_mandate_id", table_name="proposal_log", schema=SCHEMA
    )
    op.drop_table("proposal_log", schema=SCHEMA)
    op.execute(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE')
