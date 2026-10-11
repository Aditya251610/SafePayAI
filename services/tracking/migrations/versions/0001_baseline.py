"""baseline: tracking schema, tables, grants

Revision ID: 0001
Revises:
Create Date: 2026-10-11

Tables per data-architecture.md section 3 (tracking row) and tracking/spec.md section 2.
Grants via libs/common's safepayai_common.db.grants helper (mig_tracking owns, svc_tracking
gets scoped grants) per data-architecture.md section 4 and conventions doc section 9.
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

SCHEMA = "tracking"
MIGRATION_ROLE = "mig_tracking"
RUNTIME_ROLE = "svc_tracking"


def upgrade() -> None:
    bind = op.get_bind()
    create_schema_and_roles(bind, SCHEMA, MIGRATION_ROLE, RUNTIME_ROLE)

    op.create_table(
        "shipments",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("order_id", sa.Text(), nullable=False),
        sa.Column("capture_id", sa.Text(), nullable=True),
        sa.Column("mandate_id", sa.Text(), nullable=True),
        sa.Column("tracking_number", sa.Text(), nullable=False),
        sa.Column("carrier_name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="LABEL_CREATED"),
        sa.Column("anomaly", sa.Text(), nullable=True),
        sa.Column("outcome_profile", sa.Text(), nullable=False, server_default="ON_TIME"),
        sa.Column("promised_at_sim", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at_sim", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paypal_tracker_id", sa.Text(), nullable=True),
        sa.Column("paypal_sync", sa.Text(), nullable=False, server_default="NOT_ATTEMPTED"),
        sa.Column("paypal_last_error", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("order_id", "tracking_number", name="uq_shipments_order_tracking"),
        schema=SCHEMA,
    )

    op.create_table(
        "scheduled_events",
        sa.Column("shipment_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("due_at_sim", sa.DateTime(timezone=True), nullable=False),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_by", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("shipment_id", "seq", name="pk_scheduled_events"),
        schema=SCHEMA,
    )

    op.create_table(
        "shipment_events",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shipment_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("occurred_at_sim", sa.DateTime(timezone=True), nullable=False),
        sa.Column("occurred_at_real", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("actor", sa.Text(), nullable=True),
        sa.Column("note_code", sa.Text(), nullable=True),
        schema=SCHEMA,
    )

    op.create_table(
        "demo_clock",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("offset_seconds", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )

    op.create_table(
        "clock_jumps",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False, unique=True),
        sa.Column("from_sim", sa.DateTime(timezone=True), nullable=False),
        sa.Column("to_sim", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )

    op.create_table(
        "detections",
        sa.Column("shipment_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("detected_at_sim", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("emitted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("shipment_id", "kind", name="pk_detections"),
        schema=SCHEMA,
    )

    op.create_table(
        "tick_lease",
        sa.Column("name", sa.Text(), primary_key=True),
        sa.Column("holder", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )

    op.create_table(
        "detector_runs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("trigger", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("detected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_lease", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema=SCHEMA,
    )

    op.create_table(
        "inbox",
        sa.Column("event_id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
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
            TableGrant("shipments", ("SELECT", "INSERT", "UPDATE")),
            TableGrant("scheduled_events", ("SELECT", "INSERT", "UPDATE")),
            TableGrant("shipment_events", ("SELECT", "INSERT")),
            TableGrant("demo_clock", ("SELECT", "INSERT", "UPDATE")),
            TableGrant("clock_jumps", ("SELECT", "INSERT")),
            TableGrant("detections", ("SELECT", "INSERT")),
            TableGrant("tick_lease", ("SELECT", "INSERT", "UPDATE")),
            TableGrant("detector_runs", ("SELECT", "INSERT", "UPDATE")),
            TableGrant("inbox", ("SELECT", "INSERT", "DELETE")),
            TableGrant("outbox", ("SELECT", "INSERT", "UPDATE", "DELETE")),
        ],
    )


def downgrade() -> None:
    for table in (
        "outbox",
        "inbox",
        "detector_runs",
        "tick_lease",
        "detections",
        "clock_jumps",
        "demo_clock",
        "shipment_events",
        "scheduled_events",
        "shipments",
    ):
        op.drop_table(table, schema=SCHEMA)
