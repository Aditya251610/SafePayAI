"""baseline: schema paypal + call_ledger/refund_ledger/ticket_nonces/control_flags/outbox + grants

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-11

Creates schema `paypal` (data-architecture.md section 3) and its tables per
paypal-adapter/spec.md sections 6 and 13 (C12 adds outbox/ticket_nonces/control_flags beyond
the two tables service-map originally listed), then grants via safepayai_common.db.grants.

NOTE (reconciled cross-service conflict, 2026-10-11): paypal-adapter/deployment.md section 2
names the runtime role "paypal_app"; data-architecture.md section 4 is the platform-wide
authority on DB roles and uses the generic `mig_<slug>`/`svc_<slug>` scheme for every other
service (including catalog and api-gateway, which also had a service-doc-specific name
overridden to match). To keep the shared CI grants-matrix test and db_grants helper consistent
across all 10 services, this migration uses `svc_paypal`/`mig_paypal`, not paypal_app.
Flagged for the paypal-adapter deployment.md owner to update that doc to match.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from safepayai_common.db.grants import TableGrant, apply_table_grants, create_schema_and_roles

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "paypal"
MIGRATION_ROLE = "mig_paypal"
RUNTIME_ROLE = "svc_paypal"


def upgrade() -> None:
    bind = op.get_bind()
    # create_schema_and_roles (safepayai_common.db.grants) only creates the schema and
    # grants USAGE -- it has no CREATE ROLE (audit's baseline docstring notes the same).
    # Fixed here the same way mandate's 0001_baseline.py does: create the role first if
    # missing (Wave 4 never did this, so a fresh DB failed with "role does not exist").
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

    op.execute(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"')
    pg_uuid = sa.dialects.postgresql.UUID(as_uuid=True)
    jsonb = sa.dialects.postgresql.JSONB

    op.create_table(
        "call_ledger",
        sa.Column("request_id", pg_uuid, primary_key=True),
        sa.Column("op", sa.String(length=32), nullable=False),
        sa.Column("caller", sa.String(length=32), nullable=False),
        sa.Column("ticket_tid", pg_uuid, nullable=True),
        sa.Column("body_sha256", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("paypal_http_status", sa.Integer(), nullable=True),
        sa.Column("paypal_object_id", sa.String(length=64), nullable=True),
        sa.Column("response_json_redacted", jsonb, nullable=True),
        sa.Column(
            "created", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema=SCHEMA,
    )

    op.create_table(
        "refund_ledger",
        sa.Column("refund_id", sa.String(length=64), primary_key=True),
        sa.Column("request_id", pg_uuid, nullable=False),
        sa.Column("capture_id", sa.String(length=64), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), nullable=False, server_default="USD"),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_paypal_refund_ledger_capture_id", "refund_ledger", ["capture_id"], schema=SCHEMA
    )

    op.create_table(
        "ticket_nonces",
        sa.Column("tid", pg_uuid, primary_key=True),
        sa.Column("request_id", pg_uuid, nullable=False),
        sa.Column("body_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema=SCHEMA,
    )

    op.create_table(
        "control_flags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("money_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("frozen", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema=SCHEMA,
    )

    op.create_table(
        "outbox",
        sa.Column("seq", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_id", pg_uuid, nullable=False, unique=True),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.Text(), nullable=True),
        sa.Column("payload", jsonb, nullable=False),
        sa.Column("trace_id", pg_uuid, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        schema=SCHEMA,
    )

    conn = op.get_bind()
    create_schema_and_roles(conn, SCHEMA, MIGRATION_ROLE, RUNTIME_ROLE)
    apply_table_grants(
        conn,
        SCHEMA,
        RUNTIME_ROLE,
        [
            TableGrant("call_ledger", ("INSERT", "SELECT", "UPDATE")),
            TableGrant("refund_ledger", ("INSERT", "SELECT")),
            TableGrant("ticket_nonces", ("INSERT", "SELECT")),
            TableGrant("control_flags", ("SELECT", "UPDATE")),
            TableGrant("outbox", ("INSERT", "SELECT", "UPDATE")),
        ],
    )
    # CLAUDE.md known recurring failure class: a SERIAL/BIGSERIAL PK needs
    # GRANT USAGE ON SEQUENCE in addition to GRANT INSERT ON TABLE -- the latter does
    # not imply the former. outbox.seq is bigserial.
    conn.execute(sa.text(f'GRANT USAGE ON SEQUENCE "{SCHEMA}".outbox_seq_seq TO "{RUNTIME_ROLE}"'))


def downgrade() -> None:
    for table in ("outbox", "control_flags", "ticket_nonces", "refund_ledger", "call_ledger"):
        op.drop_table(table, schema=SCHEMA)
    op.execute(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE')
