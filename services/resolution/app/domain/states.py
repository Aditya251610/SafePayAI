"""Case state enum, transition specs (T1-T27), legal-transition table, and case-machine exceptions.

Implements resolution/spec.md section 3 (12-state machine, transition table T1-T27), section 2
(case kinds and origins) and section 13 (CAS on version). The table is data; the only mutation
path is usecases/transitions.apply_transition (spec s3 property). Pure module.
Scaffold only: is_legal_transition's body is yours to write.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CaseState(StrEnum):
    """The 12 case states (spec s3). UI shows only 5 key states (sprint S3 demo), not all 12."""

    PROTECTED = "PROTECTED"
    MONITORING = "MONITORING"
    PROBLEM_DETECTED = "PROBLEM_DETECTED"
    TRIAGED = "TRIAGED"
    OFFERED = "OFFERED"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    APPROVED = "APPROVED"
    REFUNDING = "REFUNDING"
    RESOLVED_REFUNDED = "RESOLVED_REFUNDED"
    RESOLVED_RESHIP = "RESOLVED_RESHIP"
    DECLINED = "DECLINED"
    CLOSED = "CLOSED"


class CaseKind(StrEnum):
    """Case kind (spec s2). Set only by triage-ai enum or the detector; never from the client."""

    LATE = "LATE"
    LOST = "LOST"
    DAMAGED = "DAMAGED"
    WRONG_ITEM = "WRONG_ITEM"
    NOT_AS_DESCRIBED = "NOT_AS_DESCRIBED"
    OTHER = "OTHER"


class CaseOrigin(StrEnum):
    """Who opened the case (spec s2)."""

    DETECTOR = "DETECTOR"
    BUYER_REPORT = "BUYER_REPORT"


class Actor(StrEnum):
    """Actor recorded on every case_transitions row (spec s3 table 'actor' column)."""

    SYSTEM = "system"
    BUYER = "buyer"
    MERCHANT = "merchant"
    REVIEWER = "reviewer"
    MANDATE_PREAUTH = "mandate_preauth"


@dataclass(frozen=True, slots=True)
class TransitionSpec:
    """One row of the spec s3 table: id, endpoints, trigger text, actor and guard."""

    transition_id: str  # "T1".."T27"
    from_state: CaseState
    to_state: CaseState
    trigger: str
    actor: str  # one or more Actor values, '/'-joined as in the spec ("system/buyer")
    guard: str


class IllegalTransition(Exception):
    """Transition not in LEGAL_TRANSITIONS; maps to HTTP 409 ILLEGAL_TRANSITION."""


class ConcurrentModification(Exception):
    """Version CAS lost (rowcount 0 on UPDATE ... WHERE version = :v); maps to HTTP 409."""


# Every row of the spec s3 transition table, in spec order. Data only.
TRANSITIONS: tuple[TransitionSpec, ...] = (
    TransitionSpec(
        "T1",
        CaseState.PROTECTED,
        CaseState.MONITORING,
        "shipment exists (materialization)",
        "system",
        "",
    ),
    TransitionSpec(
        "T2",
        CaseState.PROTECTED,
        CaseState.PROBLEM_DETECTED,
        "buyer report with no shipment, or lost/late signal",
        "system/buyer",
        "",
    ),
    TransitionSpec(
        "T3",
        CaseState.MONITORING,
        CaseState.PROBLEM_DETECTED,
        "late/lost signal or buyer report",
        "system/buyer",
        "(order_id,kind) unique",
    ),
    TransitionSpec(
        "T4",
        CaseState.MONITORING,
        CaseState.CLOSED,
        "delivered and protection window ended without problem",
        "system",
        "only via tracking fact; effectively unused in v1",
    ),
    TransitionSpec(
        "T5",
        CaseState.PROBLEM_DETECTED,
        CaseState.TRIAGED,
        "triage ok or detector origin (kind known)",
        "system",
        "",
    ),
    TransitionSpec(
        "T6",
        CaseState.PROBLEM_DETECTED,
        CaseState.HUMAN_REVIEW,
        "triage failure/timeout/low confidence/injection flag/kind-vs-carrier disagreement",
        "system",
        "fail closed",
    ),
    TransitionSpec(
        "T7",
        CaseState.TRIAGED,
        CaseState.OFFERED,
        "policy class INSIDE_TERMS or OUTSIDE_TERMS",
        "system",
        "offer/proposal persisted",
    ),
    TransitionSpec(
        "T8",
        CaseState.TRIAGED,
        CaseState.HUMAN_REVIEW,
        "policy class HUMAN_REVIEW",
        "system",
        "",
    ),
    TransitionSpec(
        "T9",
        CaseState.OFFERED,
        CaseState.APPROVED,
        "buyer accepts INSIDE_TERMS offer, consents via approval link, or pre-auth auto-accept (tier 0)",
        "buyer/mandate_preauth",
        "offer ACTIVE, hash match",
    ),
    TransitionSpec(
        "T10",
        CaseState.OFFERED,
        CaseState.RESOLVED_RESHIP,
        "buyer chose RESHIP offer and merchant confirms reship",
        "buyer then merchant",
        "RESHIP offers only",
    ),
    TransitionSpec(
        "T11",
        CaseState.OFFERED,
        CaseState.DECLINED,
        "buyer declines the offer",
        "buyer",
        "reason code from enum",
    ),
    TransitionSpec(
        "T12",
        CaseState.OFFERED,
        CaseState.HUMAN_REVIEW,
        "offer/link expired, merchant override requested review, or facts changed (hash mismatch)",
        "system",
        "no auto-deny, window held",
    ),
    TransitionSpec(
        "T13",
        CaseState.HUMAN_REVIEW,
        CaseState.OFFERED,
        "reviewer decision creates an offer/proposal (never a direct refund)",
        "reviewer",
        "permitted paths only",
    ),
    TransitionSpec(
        "T14",
        CaseState.HUMAN_REVIEW,
        CaseState.DECLINED,
        "reviewer declines with written reason",
        "reviewer",
        "reason mandatory, audited",
    ),
    TransitionSpec(
        "T15",
        CaseState.HUMAN_REVIEW,
        CaseState.CLOSED,
        "reviewer closes (duplicate/delivered/buyer withdrew)",
        "reviewer",
        "reason mandatory",
    ),
    TransitionSpec(
        "T16",
        CaseState.APPROVED,
        CaseState.REFUNDING,
        "all 9 checks pass; CAS",
        "system",
        "single winner",
    ),
    TransitionSpec(
        "T17",
        CaseState.APPROVED,
        CaseState.HUMAN_REVIEW,
        "a check fails for a non-transient reason",
        "system",
        "records failed check",
    ),
    TransitionSpec(
        "T18",
        CaseState.REFUNDING,
        CaseState.RESOLVED_REFUNDED,
        "attempt COMPLETED (reconciled or direct)",
        "system",
        "PayPal COMPLETED",
    ),
    TransitionSpec(
        "T19",
        CaseState.REFUNDING,
        CaseState.HUMAN_REVIEW,
        "attempt FAILED or reconcile retries exhausted",
        "system",
        "",
    ),
    TransitionSpec(
        "T20",
        CaseState.REFUNDING,
        CaseState.APPROVED,
        "adapter confirms NOT SENT (frozen, pre-flight reject)",
        "system",
        "attempt marked NOT_SENT; no PayPal call",
    ),
    TransitionSpec(
        "T21",
        CaseState.RESOLVED_REFUNDED,
        CaseState.CLOSED,
        "notification sent, grace over",
        "system",
        "",
    ),
    TransitionSpec(
        "T22", CaseState.RESOLVED_RESHIP, CaseState.CLOSED, "same as T21", "system", ""
    ),
    TransitionSpec(
        "T23", CaseState.DECLINED, CaseState.CLOSED, "after appeal window", "system", ""
    ),
    TransitionSpec(
        "T24", CaseState.DECLINED, CaseState.HUMAN_REVIEW, "buyer appeals", "buyer", ""
    ),
    TransitionSpec(
        "T25",
        CaseState.DECLINED,
        CaseState.OFFERED,
        "merchant override (NEW offer, buyer approval needed)",
        "merchant",
        "creates new proposal/hash",
    ),
    TransitionSpec(
        "T26",
        CaseState.OFFERED,
        CaseState.OFFERED,
        "merchant override supersedes active offer",
        "merchant",
        "old offer SUPERSEDED, tokens revoked, version bumps",
    ),
    TransitionSpec(
        "T27",
        CaseState.HUMAN_REVIEW,
        CaseState.HUMAN_REVIEW,
        "kind escalation LATE->LOST or new evidence",
        "system",
        "audit only (P2)",
    ),
)

# Legal (from -> {to}) map derived by hand from TRANSITIONS above. Data only.
# Terminal for money: RESOLVED_REFUNDED, RESOLVED_RESHIP, CLOSED (spec s3 notes).
LEGAL_TRANSITIONS: dict[CaseState, frozenset[CaseState]] = {
    CaseState.PROTECTED: frozenset({CaseState.MONITORING, CaseState.PROBLEM_DETECTED}),
    CaseState.MONITORING: frozenset({CaseState.PROBLEM_DETECTED, CaseState.CLOSED}),
    CaseState.PROBLEM_DETECTED: frozenset({CaseState.TRIAGED, CaseState.HUMAN_REVIEW}),
    CaseState.TRIAGED: frozenset({CaseState.OFFERED, CaseState.HUMAN_REVIEW}),
    CaseState.OFFERED: frozenset(
        {
            CaseState.APPROVED,
            CaseState.RESOLVED_RESHIP,
            CaseState.DECLINED,
            CaseState.HUMAN_REVIEW,
            CaseState.OFFERED,
        }
    ),
    CaseState.HUMAN_REVIEW: frozenset(
        {
            CaseState.OFFERED,
            CaseState.DECLINED,
            CaseState.CLOSED,
            CaseState.HUMAN_REVIEW,
        }
    ),
    CaseState.APPROVED: frozenset({CaseState.REFUNDING, CaseState.HUMAN_REVIEW}),
    CaseState.REFUNDING: frozenset(
        {CaseState.RESOLVED_REFUNDED, CaseState.HUMAN_REVIEW, CaseState.APPROVED}
    ),
    CaseState.RESOLVED_REFUNDED: frozenset({CaseState.CLOSED}),
    CaseState.RESOLVED_RESHIP: frozenset({CaseState.CLOSED}),
    CaseState.DECLINED: frozenset(
        {CaseState.CLOSED, CaseState.HUMAN_REVIEW, CaseState.OFFERED}
    ),
    CaseState.CLOSED: frozenset(),
}


def is_legal_transition(from_state: CaseState, to_state: CaseState) -> bool:
    """Return True if from_state -> to_state appears in LEGAL_TRANSITIONS.

    Inputs: two CaseState values. Output: bool; caller raises IllegalTransition on False.
    Edge cases: self-loops exist only for OFFERED (T26) and HUMAN_REVIEW (T27).
    """
    return to_state in LEGAL_TRANSITIONS.get(from_state, frozenset())
