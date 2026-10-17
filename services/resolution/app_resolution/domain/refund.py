"""Refund attempt statuses, legal attempt transitions, and the saga's result mapping types.

Implements resolution/spec.md section 7 (refund execution: REQUESTED -> SENT -> COMPLETED | FAILED |
UNKNOWN, plus NOT_SENT) and section 8 (reconcile). Pure module. The attempt table is data; the
saga orchestration (check 9 transaction, adapter call, interpretation) is in usecases/execute_refund.py.
Scaffold only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class RefundAttemptStatus(StrEnum):
    """Attempt states (spec s7 'Attempt state'). One attempt per case, ever (spec s7 item 4)."""

    REQUESTED = "REQUESTED"  # committed with check 9, before any PayPal call
    SENT = "SENT"  # HTTP call returned or timed out; PayPal may or may not have it
    COMPLETED = "COMPLETED"  # terminal success
    FAILED = "FAILED"  # terminal failure (e.g. 422 REFUND_AMOUNT_EXCEEDED)
    UNKNOWN = "UNKNOWN"  # timeout/5xx/connection error; reconcile decides
    NOT_SENT = (
        "NOT_SENT"  # adapter refused pre-flight (frozen/ceiling/ticket); no PayPal call
    )


# Legal attempt transitions (spec s7 + s8). Data only. Terminal: COMPLETED, FAILED, NOT_SENT.
ATTEMPT_TRANSITIONS: dict[RefundAttemptStatus, frozenset[RefundAttemptStatus]] = {
    RefundAttemptStatus.REQUESTED: frozenset(
        {RefundAttemptStatus.SENT, RefundAttemptStatus.NOT_SENT}
    ),
    RefundAttemptStatus.SENT: frozenset(
        {
            RefundAttemptStatus.COMPLETED,
            RefundAttemptStatus.FAILED,
            RefundAttemptStatus.UNKNOWN,
        }
    ),
    RefundAttemptStatus.UNKNOWN: frozenset(
        {
            RefundAttemptStatus.SENT,
            RefundAttemptStatus.COMPLETED,
            RefundAttemptStatus.FAILED,
        }
    ),
    RefundAttemptStatus.COMPLETED: frozenset(),
    RefundAttemptStatus.FAILED: frozenset(),
    RefundAttemptStatus.NOT_SENT: frozenset(),
}

# Statuses that count as "money in flight or done" for the partial unique index (spec s13):
# one live attempt per order, enforced by the DB as well as by check 7.
LIVE_ATTEMPT_STATUSES: frozenset[RefundAttemptStatus] = frozenset(
    {
        RefundAttemptStatus.REQUESTED,
        RefundAttemptStatus.SENT,
        RefundAttemptStatus.UNKNOWN,
        RefundAttemptStatus.COMPLETED,
    }
)


@dataclass(frozen=True, slots=True)
class RefundAttemptRecord:
    """In-memory view of one refund_attempts row (spec s2, s7, s13)."""

    attempt_id: UUID
    case_id: UUID
    order_id: UUID
    request_id: UUID  # PayPal-Request-Id, persisted BEFORE the call (spec s7 item 1)
    invoice_id: str  # "PS-" + case_id, unique (spec s7)
    capture_id: str
    amount_minor: int
    currency: str
    status: RefundAttemptStatus
    paypal_refund_id: str | None
    reconcile_count: int
    sent_at: datetime | None


def is_legal_attempt_transition(
    from_status: RefundAttemptStatus, to_status: RefundAttemptStatus
) -> bool:
    """Return True if from_status -> to_status is in ATTEMPT_TRANSITIONS.

    Inputs: two attempt statuses. Output: bool; caller treats False as a programming error.
    Edge cases: UNKNOWN -> SENT is the reconcile path (spec s7); terminal states have no exits.
    """
    return to_status in ATTEMPT_TRANSITIONS.get(from_status, frozenset())
