"""baseline: resolution schema, tables, grants, REFUNDS_FROZEN seed

Revision ID: 0001
Revises:
Create Date: 2026-10-11

Tables per data-architecture.md section 3 (resolution row) and resolution/spec.md section 1
(`cases, case_transitions, case_signals, offers, approvals, policy_decisions,
refund_attempts, notifications, control_flags, idempotency_keys, outbox, inbox_dedupe`).
Seeds `control_flags` with refunds_frozen=true (deployment.md section 6: migration 0001
"seeds the control_flags row with refunds_frozen = true" — the global kill switch defaults
closed). Grants via libs/common's safepayai_common.db.grants helper.
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

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "resolution"
MIGRATION_ROLE = "mig_resolution"
RUNTIME_ROLE = "svc_resolution"


def upgrade() -> None:
    bind = op.get_bind()
    # Idempotent local/CI role bootstrap (CLAUDE.md "known recurring failure classes" -
    # create_schema_and_roles only GRANTs, it never CREATEs; without this block it fails with
    # "role does not exist" on a fresh DB, a bug independently found and fixed in two other
    # services' baseline migrations this session).
    for role in (MIGRATION_ROLE, RUNTIME_ROLE):
        bind.execute(
            sa.text(
                f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                        CREATE ROLE "{role}" NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS LOGIN;
                    END IF;
                END $$;
                """
            )
        )
    create_schema_and_roles(bind, SCHEMA, MIGRATION_ROLE, RUNTIME_ROLE)

    op.create_table(
        "cases",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("order_id", sa.Text(), nullable=False),
        sa.Column("capture_id", sa.Text(), nullable=True),
        sa.Column("mandate_id", sa.Text(), nullable=True),
        sa.Column("buyer_id", sa.Text(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="PROTECTED"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("terms_snapshot", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("terms_hash", sa.Text(), nullable=True),
        sa.Column(
            "opened_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "window_hold", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("amount_minor", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.CHAR(3), nullable=True),
        sa.Column("triage", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("untrusted_text", sa.Text(), nullable=True),
        sa.Column("human_review_reason", sa.Text(), nullable=True),
        sa.Column("human_review_entered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.UniqueConstraint("order_id", "kind", name="uq_cases_order_kind"),
        sa.CheckConstraint(
            "amount_minor IS NULL OR amount_minor > 0", name="ck_cases_amount_positive"
        ),
        schema=SCHEMA,
    )

    op.create_table(
        "case_transitions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("from_state", sa.Text(), nullable=True),
        sa.Column("to_state", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_case_transitions_case_id_at",
        "case_transitions",
        ["case_id", "at"],
        schema=SCHEMA,
    )

    op.create_table(
        "case_signals",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("payload", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        schema=SCHEMA,
    )

    op.create_table(
        "offers",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.CHAR(3), nullable=False),
        sa.Column("tier", sa.Text(), nullable=False),
        sa.Column("proposal_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="ACTIVE"),
        sa.Column("offer_seq", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_offers_case_id", "offers", ["case_id"], schema=SCHEMA)

    op.create_table(
        "approvals",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tid", sa.Text(), nullable=False),
        sa.Column(
            "proposal_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("proposal_hash", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="issued"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tid", name="uq_approvals_tid"),
        sa.UniqueConstraint("proposal_id", name="uq_approvals_proposal_id"),
        sa.UniqueConstraint("token_hash", name="uq_approvals_token_hash"),
        schema=SCHEMA,
    )

    op.create_table(
        "policy_decisions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("klass", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column("reasons", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("facts_hash", sa.Text(), nullable=True),
        sa.Column("checks", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        schema=SCHEMA,
    )

    op.create_table(
        "refund_attempts",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", sa.Text(), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("invoice_id", sa.Text(), nullable=False),
        # Added (Wave 5B): models.py already declared these (spec s7: capture_id and currency
        # are part of every refund attempt) but the baseline migration's DDL was missing them -
        # caught by the first real integration test against this table.
        sa.Column("capture_id", sa.Text(), nullable=False, server_default=""),
        sa.Column("currency", sa.CHAR(3), nullable=False, server_default="USD"),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="REQUESTED"),
        sa.Column("paypal_refund_id", sa.Text(), nullable=True),
        sa.Column("reconcile_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.UniqueConstraint("case_id", name="uq_refund_attempts_case_id"),
        sa.UniqueConstraint("invoice_id", name="uq_refund_attempts_invoice_id"),
        sa.UniqueConstraint("request_id", name="uq_refund_attempts_request_id"),
        schema=SCHEMA,
    )
    op.create_index(
        "ux_refund_attempts_order_inflight",
        "refund_attempts",
        ["order_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text(
            "status IN ('REQUESTED','SENT','UNKNOWN','COMPLETED')"
        ),
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("buyer_id", sa.Text(), nullable=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        schema=SCHEMA,
    )

    op.create_table(
        "control_flags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("refunds_frozen", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("set_by", sa.Text(), nullable=True),
        sa.Column("set_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("epoch", sa.Integer(), nullable=False, server_default="0"),
        schema=SCHEMA,
    )

    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("route", sa.Text(), nullable=False),
        sa.Column("principal", sa.Text(), nullable=True),
        sa.Column("request_hash", sa.Text(), nullable=True),
        sa.Column("response", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.UniqueConstraint("key", "route", name="uq_idempotency_keys_key_route"),
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
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("aggregate_id", sa.Text(), nullable=False),
        sa.Column("payload", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("trace_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "delivered_to",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )

    op.create_table(
        "inbox_dedupe",
        sa.Column(
            "event_id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True
        ),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )

    # Known failure class (CLAUDE.md "sequence grants"): a bigserial PK (outbox.seq) needs
    # GRANT USAGE ON SEQUENCE in addition to GRANT INSERT ON TABLE.
    bind.execute(
        sa.text(
            f'GRANT USAGE, SELECT ON SEQUENCE "{SCHEMA}"."outbox_seq_seq" TO "{RUNTIME_ROLE}"'
        )
    )

    apply_table_grants(
        bind,
        SCHEMA,
        RUNTIME_ROLE,
        [
            TableGrant("cases", ("SELECT", "INSERT", "UPDATE")),
            TableGrant("case_transitions", ("SELECT", "INSERT")),
            TableGrant("case_signals", ("SELECT", "INSERT")),
            TableGrant("offers", ("SELECT", "INSERT", "UPDATE")),
            TableGrant("approvals", ("SELECT", "INSERT", "UPDATE")),
            TableGrant("policy_decisions", ("SELECT", "INSERT")),
            TableGrant("refund_attempts", ("SELECT", "INSERT", "UPDATE")),
            TableGrant("notifications", ("SELECT", "INSERT")),
            TableGrant("control_flags", ("SELECT", "UPDATE")),
            TableGrant("idempotency_keys", ("SELECT", "INSERT", "DELETE")),
            TableGrant("outbox", ("SELECT", "INSERT", "UPDATE", "DELETE")),
            TableGrant("inbox_dedupe", ("SELECT", "INSERT", "DELETE")),
        ],
    )

    # Seed REFUNDS_FROZEN = true (fail closed; deployment.md section 6/7). This value is
    # hardcoded true here, NOT read from PS_RESOLUTION_REFUNDS_FROZEN_DEFAULT, because that
    # setting may only ever be used to seed a first row and must never be false at seed time.
    op.execute(
        sa.text(
            f'INSERT INTO "{SCHEMA}".control_flags (id, refunds_frozen, reason, set_by, epoch) '
            "VALUES (1, true, 'seeded at migration', 'system', 0)"
        )
    )


def downgrade() -> None:
    for table in (
        "inbox_dedupe",
        "outbox",
        "idempotency_keys",
        "control_flags",
        "notifications",
        "refund_attempts",
        "policy_decisions",
        "approvals",
        "offers",
        "case_signals",
        "case_transitions",
        "cases",
    ):
        op.drop_table(table, schema=SCHEMA)
