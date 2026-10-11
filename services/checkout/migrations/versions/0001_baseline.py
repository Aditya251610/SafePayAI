"""baseline: schema checkout + tables + grants

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-11

Creates schema `checkout` (data-architecture.md section 3) and its tables per
checkout/spec.md section 2, then grants via safepayai_common.db.grants.

NOTE (reconciled cross-service conflict, 2026-10-11): checkout/spec.md section 2 names the
runtime role "checkout_app"; data-architecture.md section 4 is the platform-wide authority on
DB roles and uses the generic `mig_<slug>`/`svc_<slug>` scheme for every other service
(including catalog and api-gateway, which also had a service-doc-specific name overridden to
match). To keep the shared CI grants-matrix test and db_grants helper consistent across all
10 services, this migration uses `svc_checkout`/`mig_checkout`, not checkout_app. Flagged for
the checkout spec.md owner to update that doc to match.
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

SCHEMA = "checkout"
MIGRATION_ROLE = "mig_checkout"
RUNTIME_ROLE = "svc_checkout"


def upgrade() -> None:
    op.execute(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"')
    pg_uuid = sa.dialects.postgresql.UUID(as_uuid=True)
    jsonb = sa.dialects.postgresql.JSONB

    op.create_table(
        "carts",
        sa.Column("cart_id", pg_uuid, primary_key=True),
        sa.Column("buyer_id", pg_uuid, nullable=False),
        sa.Column("mandate_id", pg_uuid, nullable=False),
        sa.Column("mandate_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("lines", jsonb, nullable=False),
        sa.Column("total_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), nullable=False, server_default="USD"),
        sa.Column("merchant_ids", jsonb, nullable=False, server_default="[]"),
        sa.Column("catalog_version", sa.String(length=32), nullable=True),
        sa.Column("proposal_hash", sa.String(length=64), nullable=True),
        sa.Column("intent_fit_verdict", sa.String(length=32), nullable=True),
        sa.Column("intent_fit_reason_code", sa.String(length=32), nullable=True),
        sa.Column("intent_fit_confidence", sa.Float(), nullable=True),
        sa.Column(
            "stated_price_mismatch",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("committed_minor_at_check", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("total_minor > 0", name="ck_carts_total_minor_positive"),
        sa.CheckConstraint("currency = 'USD'", name="ck_carts_currency_usd"),
        schema=SCHEMA,
    )

    op.create_table(
        "cart_checks",
        sa.Column("id", pg_uuid, primary_key=True),
        sa.Column("cart_id", pg_uuid, nullable=False),
        sa.Column("phase", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_checkout_cart_checks_cart_id", "cart_checks", ["cart_id"], schema=SCHEMA
    )

    op.create_table(
        "orders",
        sa.Column("order_id", pg_uuid, primary_key=True),
        sa.Column("cart_id", pg_uuid, nullable=False, unique=True),
        sa.Column("buyer_id", pg_uuid, nullable=False),
        sa.Column("mandate_id", pg_uuid, nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("total_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), nullable=False, server_default="USD"),
        sa.Column("paypal_order_id", sa.String(length=64), nullable=True, unique=True),
        sa.Column("create_request_id", pg_uuid, nullable=True),
        sa.Column("capture_request_id", pg_uuid, nullable=True),
        sa.Column("custom_id", sa.String(length=64), nullable=True),
        sa.Column("invoice_id", sa.String(length=64), nullable=True, unique=True),
        sa.Column("approve_url", sa.Text(), nullable=True),
        sa.Column("last_paypal_status", sa.String(length=32), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_checkout_orders_mandate_id", "orders", ["mandate_id"], schema=SCHEMA
    )

    op.create_table(
        "captures",
        sa.Column("capture_id", sa.String(length=64), primary_key=True),
        sa.Column("order_id", pg_uuid, nullable=False, unique=True),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), nullable=False, server_default="USD"),
        sa.Column("paypal_status", sa.String(length=32), nullable=True),
        sa.Column("custom_id", sa.String(length=64), nullable=True),
        sa.Column("invoice_id", sa.String(length=64), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_checkout_captures_order_id",
        "captures",
        ["order_id"],
        schema=SCHEMA,
        unique=True,
    )

    op.create_table(
        "receipts",
        sa.Column("order_id", pg_uuid, primary_key=True),
        sa.Column("receipt_json", jsonb, nullable=False),
        sa.Column("mandate_hash", sa.String(length=64), nullable=True),
        sa.Column("audit_event_id", pg_uuid, nullable=True),
        sa.Column("protection_window_days", sa.Integer(), nullable=True),
        sa.Column("remaining_cap_minor", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema=SCHEMA,
    )

    op.create_table(
        "return_bindings",
        sa.Column("state_hash", sa.String(length=64), primary_key=True),
        sa.Column("order_id", pg_uuid, nullable=False),
        sa.Column("buyer_id", pg_uuid, nullable=False),
        sa.Column("mandate_id", pg_uuid, nullable=False),
        sa.Column("paypal_order_id", sa.String(length=64), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("exp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )

    op.create_table(
        "idempotency_keys",
        sa.Column("principal", sa.String(length=64), primary_key=True),
        sa.Column("route", sa.String(length=128), primary_key=True),
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_code", sa.Integer(), nullable=True),
        sa.Column("response_body", jsonb, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema=SCHEMA,
    )

    op.create_table(
        "inbox",
        sa.Column("event_id", pg_uuid, primary_key=True),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema=SCHEMA,
    )

    op.create_table(
        "outbox",
        sa.Column("seq", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_id", pg_uuid, nullable=False, unique=True),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", pg_uuid, nullable=False),
        sa.Column("payload", jsonb, nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        schema=SCHEMA,
    )

    conn = op.get_bind()
    # Idempotent local/CI role bootstrap (data-architecture.md section 1), matching
    # catalog/mandate's baseline migration pattern -- without this, create_schema_and_roles
    # below (which only grants, never creates) fails with "role does not exist" at runtime.
    for role in (MIGRATION_ROLE, RUNTIME_ROLE):
        conn.execute(
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
    create_schema_and_roles(conn, SCHEMA, MIGRATION_ROLE, RUNTIME_ROLE)
    # Known failure class (CLAUDE.md "sequence grants"): a bigserial PK (outbox.seq)
    # needs GRANT USAGE ON SEQUENCE in addition to GRANT INSERT ON TABLE - the latter
    # does not imply the former, and INSERT without it fails at runtime, not at
    # migration time, so it is easy to miss until the first real write.
    conn.execute(
        sa.text(
            f'GRANT USAGE, SELECT ON SEQUENCE "{SCHEMA}"."outbox_seq_seq" TO "{RUNTIME_ROLE}"'
        )
    )
    apply_table_grants(
        conn,
        SCHEMA,
        RUNTIME_ROLE,
        [
            TableGrant("carts", ("INSERT", "SELECT", "UPDATE")),
            TableGrant("cart_checks", ("INSERT", "SELECT")),
            TableGrant("orders", ("INSERT", "SELECT", "UPDATE")),
            TableGrant("captures", ("INSERT", "SELECT")),
            TableGrant("receipts", ("INSERT", "SELECT")),
            TableGrant("return_bindings", ("INSERT", "SELECT", "UPDATE")),
            TableGrant("idempotency_keys", ("INSERT", "SELECT")),
            TableGrant("inbox", ("INSERT", "SELECT")),
            TableGrant("outbox", ("INSERT", "SELECT", "UPDATE")),
        ],
    )


def downgrade() -> None:
    for table in (
        "outbox",
        "inbox",
        "idempotency_keys",
        "return_bindings",
        "receipts",
        "captures",
        "orders",
        "cart_checks",
        "carts",
    ):
        op.drop_table(table, schema=SCHEMA)
    op.execute(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE')
