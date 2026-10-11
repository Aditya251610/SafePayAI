"""Outbound event envelopes and payloads for resolution's `case.*`/`refund.*` outbox events.

Implements resolution/spec.md section 3 (case.state_changed emitted in the same tx as every
transition), section 5 (offer.created), section 7 (refund.requested/completed/failed/unknown)
and section 9 (refund.freeze_changed). Mirrors tracking/app/schemas/events.py's envelope shape
(spec overview section 7): event_id, type, version, occurred_at, producer, aggregate_id,
trace_id, payload. All models use extra="forbid": no free text, no notes beyond enum/id fields
(CLAUDE.md honesty rules + threat B8 - buyer-visible wording never leaks into events).
"""

from __future__ import annotations

from datetime import datetime
from typing import Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict

PayloadT = TypeVar("PayloadT", bound=BaseModel)

EventType = Literal[
    "case.state_changed",
    "offer.created",
    "refund.requested",
    "refund.completed",
    "refund.failed",
    "refund.unknown",
    "refund.blocked_frozen",
    "refund.freeze_changed",
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CaseStateChangedPayload(_Strict):
    """spec s3: emitted in the same transaction as every applied case transition."""

    case_id: UUID
    order_id: str
    kind: str
    transition_id: str  # "T1".."T27"
    from_state: str | None
    to_state: str
    version: int
    reason_code: str | None = None


class OfferCreatedPayload(_Strict):
    """spec s5: offer/proposal persisted (T7)."""

    case_id: UUID
    offer_id: UUID
    offer_seq: int
    action: str  # Action value
    amount_minor: int
    currency: str
    tier: str  # ApprovalTier value
    proposal_hash: str


class RefundRequestedPayload(_Strict):
    """spec s7 step 1: durable intent committed (check 9) before any PayPal call."""

    case_id: UUID
    order_id: str
    attempt_id: UUID
    request_id: UUID
    invoice_id: str
    capture_id: str
    amount_minor: int
    currency: str


class RefundCompletedPayload(_Strict):
    """spec s7: attempt COMPLETED (T18)."""

    case_id: UUID
    order_id: str
    attempt_id: UUID
    paypal_refund_id: str
    amount_minor: int
    currency: str


class RefundFailedPayload(_Strict):
    """spec s7: attempt FAILED (T19). reason_code is a stable enum/short code, never free text."""

    case_id: UUID
    order_id: str
    attempt_id: UUID
    reason_code: str
    amount_minor: int
    currency: str


class RefundUnknownPayload(_Strict):
    """spec s7/s8: attempt UNKNOWN after timeout/5xx; reconcile will decide."""

    case_id: UUID
    order_id: str
    attempt_id: UUID
    reconcile_count: int


class RefundBlockedFrozenPayload(_Strict):
    """spec s6 check 1: stayed APPROVED, no attempt row, queued for retry on unfreeze."""

    case_id: UUID
    order_id: str


class RefundFreezeChangedPayload(_Strict):
    """spec s9: kill-switch toggle, audited. reason is a short enum code, never free text."""

    refunds_frozen: bool
    reason_code: str
    set_by: str
    epoch: int
    adapter_mirror: Literal["ACKED", "PENDING"]


class EventEnvelope(_Strict, Generic[PayloadT]):  # noqa: UP046 - py312 PEP 695 not used repo-wide yet
    """Generic outbox envelope; PayloadT is one of the payload models above."""

    event_id: UUID
    type: EventType
    version: Literal[1] = 1
    occurred_at: datetime  # real UTC time of the outbox insert
    producer: Literal["resolution"] = "resolution"
    aggregate_id: str  # case_id (or "controls" for refund.freeze_changed) as string
    trace_id: str | None = None
    payload: PayloadT


class CaseStateChangedEvent(EventEnvelope[CaseStateChangedPayload]):
    """Concrete envelope for case.state_changed."""


class OfferCreatedEvent(EventEnvelope[OfferCreatedPayload]):
    """Concrete envelope for offer.created."""


class RefundRequestedEvent(EventEnvelope[RefundRequestedPayload]):
    """Concrete envelope for refund.requested."""


class RefundCompletedEvent(EventEnvelope[RefundCompletedPayload]):
    """Concrete envelope for refund.completed."""


class RefundFailedEvent(EventEnvelope[RefundFailedPayload]):
    """Concrete envelope for refund.failed."""


class RefundUnknownEvent(EventEnvelope[RefundUnknownPayload]):
    """Concrete envelope for refund.unknown."""


class RefundBlockedFrozenEvent(EventEnvelope[RefundBlockedFrozenPayload]):
    """Concrete envelope for refund.blocked_frozen."""


class RefundFreezeChangedEvent(EventEnvelope[RefundFreezeChangedPayload]):
    """Concrete envelope for refund.freeze_changed."""
