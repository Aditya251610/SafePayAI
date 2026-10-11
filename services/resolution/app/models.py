"""SQLAlchemy 2 table definitions for schema `resolution` (ORM types only, not migrations).

Implements resolution/spec.md section 2 (cases), section 3 (case_transitions), section 5 (offers) and
section 7/13 (refund_attempts, with the one-live-attempt-per-order partial unique index). Migrations are
hand-written and do NOT use this metadata (migrations/env.py has target_metadata=None).
Other spec tables (case_signals, approvals, policy_decisions, notifications, control_flags,
idempotency_keys, outbox, inbox_dedupe) are not scaffolded here yet.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

RESOLUTION_SCHEMA = "resolution"


class Base(DeclarativeBase):
    """Declarative base bound to the `resolution` schema (no cross-schema FKs, ADR-004)."""

    metadata = MetaData(schema=RESOLUTION_SCHEMA)


class Case(Base):
    """One case per (order_id, kind) (spec s2). Money is integer minor units; currency from capture only."""

    __tablename__ = "cases"
    __table_args__ = (UniqueConstraint("order_id", "kind", name="uq_cases_order_kind"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    capture_id: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # copied from checkout, server-derived
    mandate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    buyer_id: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # ownership check source (api s1)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # CaseKind value
    origin: Mapped[str] = mapped_column(String(16), nullable=False)  # CaseOrigin value
    state: Mapped[str] = mapped_column(String(32), nullable=False)  # CaseState value
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )  # CAS on every transition
    terms_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )  # frozen at open (C6)
    terms_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_hold: Mapped[bool] = mapped_column(nullable=False, default=False)
    amount_minor: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )  # full-order rule (spec s4)
    currency: Mapped[str | None] = mapped_column(
        String(3), nullable=True
    )  # ISO 4217, from capture
    triage: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )  # enum/confidence/flags only
    untrusted_text: Mapped[str | None] = mapped_column(
        String(4000), nullable=True
    )  # buyer text, capped
    human_review_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    human_review_entered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CaseTransition(Base):
    """Append-only history of every applied transition (spec s3). Written in the same tx as the update."""

    __tablename__ = "case_transitions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{RESOLUTION_SCHEMA}.cases.id"), nullable=False
    )
    transition_id: Mapped[str] = mapped_column(String(4), nullable=False)  # "T1".."T27"
    from_state: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )  # None for the first row
    to_state: Mapped[str] = mapped_column(String(32), nullable=False)
    version_after: Mapped[int] = mapped_column(Integer, nullable=False)
    actor: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class Offer(Base):
    """Immutable offer/proposal (spec s5). UNIQUE (case_id, offer_seq). Status moves ACTIVE -> ACCEPTED/SUPERSEDED/EXPIRED."""

    __tablename__ = "offers"
    __table_args__ = (
        UniqueConstraint("case_id", "offer_seq", name="uq_offers_case_seq"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{RESOLUTION_SCHEMA}.cases.id"), nullable=False
    )
    offer_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)  # Action value
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    tier: Mapped[str] = mapped_column(String(16), nullable=False)  # ApprovalTier value
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # OfferStatus value
    proposal_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    terms_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class RefundAttempt(Base):
    """One refund attempt per case, ever (spec s7, s13). request_id persisted BEFORE the adapter call."""

    __tablename__ = "refund_attempts"
    __table_args__ = (
        UniqueConstraint("case_id", name="uq_refund_attempts_case"),
        UniqueConstraint("invoice_id", name="uq_refund_attempts_invoice"),
        UniqueConstraint("request_id", name="uq_refund_attempts_request"),
        # One live-or-completed attempt per order (spec s13 partial unique index).
        Index(
            "uq_refund_attempts_one_live_per_order",
            "order_id",
            unique=True,
            postgresql_where=text(
                "status IN ('REQUESTED','SENT','UNKNOWN','COMPLETED')"
            ),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{RESOLUTION_SCHEMA}.cases.id"), nullable=False
    )
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )  # PayPal-Request-Id
    invoice_id: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # "PS-" + case_id
    capture_id: Mapped[str] = mapped_column(String(64), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # RefundAttemptStatus value
    paypal_refund_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reconcile_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
