"""SQLAlchemy 2 table definitions for schema `tracking` (ORM types only, not migrations).

Implements tracking/spec.md section 2 "Tables" (shipments, scheduled_events, shipment_events,
demo_clock, clock_jumps, detections, tick_lease, detector_runs, inbox, outbox) plus orders_seen
(spec C5). Migrations are hand-written in migrations/versions and do NOT use this metadata
(migrations/env.py has target_metadata=None). Keep these in sync with the DDL by hand.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Integer,
    MetaData,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

TRACKING_SCHEMA = "tracking"


class Base(DeclarativeBase):
    """Declarative base bound to the `tracking` schema (no cross-schema FKs, ADR-004)."""

    metadata = MetaData(schema=TRACKING_SCHEMA)


class Shipment(Base):
    """One shipment for one captured order (spec s2). Unique (order_id, tracking_number)."""

    __tablename__ = "shipments"
    __table_args__ = (
        UniqueConstraint(
            "order_id", "tracking_number", name="uq_shipments_order_tracking"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_id: Mapped[str] = mapped_column(String(64), nullable=False)
    capture_id: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # server-derived, never client
    mandate_id: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # server-derived, never client
    tracking_number: Mapped[str] = mapped_column(String(64), nullable=False)
    carrier_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # ShipmentStatus value
    anomaly: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )  # Anomaly value
    outcome_profile: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # OutcomeProfile value
    promised_at_sim: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at_sim: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    paypal_tracker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    paypal_sync: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # PaypalSync value
    paypal_last_error: Mapped[str | None] = mapped_column(String(128), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    demo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )  # reset scope (s3)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )  # optimistic CAS


class ScheduledEvent(Base):
    """Scripted carrier step materialised at creation (spec s2, s4 item 1). PK (shipment_id, seq)."""

    __tablename__ = "scheduled_events"

    shipment_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    due_at_sim: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # CAS column
    applied_by: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ShipmentEvent(Base):
    """Append-only history of applied transitions (spec s2). UNIQUE (shipment_id, seq)."""

    __tablename__ = "shipment_events"
    __table_args__ = (
        UniqueConstraint("shipment_id", "seq", name="uq_shipment_events_seq"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    shipment_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # TransitionSource value
    occurred_at_sim: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    occurred_at_real: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    note_code: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )  # enum only, never free text


class DemoClock(Base):
    """Singleton demo clock row, id = 1 (spec s2 demo_clock, s3)."""

    __tablename__ = "demo_clock"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    offset_seconds: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ClockJump(Base):
    """Idempotent record of each advance/reset (spec s2 clock_jumps). idempotency_key is UNIQUE."""

    __tablename__ = "clock_jumps"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    idempotency_key: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True
    )
    from_sim: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    to_sim: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Detection(Base):
    """Detection record; PK (shipment_id, kind); only the inserter emits the outbox event (s2, s4)."""

    __tablename__ = "detections"

    shipment_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    kind: Mapped[str] = mapped_column(
        String(8), primary_key=True
    )  # DetectionKind value
    detected_at_sim: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    emitted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class TickLease(Base):
    """Named lease for the single tick holder (spec s5). Uses DB clock now(), never demo clock."""

    __tablename__ = "tick_lease"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    holder: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class DetectorRun(Base):
    """One row per tick attempt for observability (spec s2 detector_runs)."""

    __tablename__ = "detector_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trigger: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # manual|inprocess|ping|external
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    applied_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    detected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_lease: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class InboxEvent(Base):
    """Inbound event dedupe; PK is the producer's event_id (spec s2 inbox)."""

    __tablename__ = "inbox"

    event_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class OutboxRow(Base):
    """Transactional outbox row written in the same tx as the state change (ADR-003, spec s2)."""

    __tablename__ = "outbox"

    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, unique=True
    )
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # PENDING|SENT|DEAD
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class OrderSeen(Base):
    """Order facts seen via order.captured event, with checkout read as fallback (spec C5)."""

    __tablename__ = "orders_seen"

    order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    capture_id: Mapped[str] = mapped_column(String(64), nullable=False)
    mandate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    protected_until_sim: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
