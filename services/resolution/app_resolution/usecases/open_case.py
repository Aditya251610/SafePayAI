"""Open-case use case: lazy materialization of a case on its first signal (late/lost/buyer report).

Implements resolution/spec.md section 2 (unique (order_id, kind), terms snapshot at open), section 3
(lazy materialization: PROTECTED -> MONITORING -> PROBLEM_DETECTED written with actor=system,
reason=materialized, T1/T2/T3) and section 10 (eligibility judged at case.opened_at, window_hold).
Idempotent: a second signal for the same (order_id, kind) is a no-op. Scaffold only.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app_resolution import clients, repo
from app_resolution.domain.policy import TermsSnapshot
from app_resolution.domain.states import Actor, CaseKind, CaseOrigin, CaseState
from app_resolution.repo import now_utc


@dataclass(frozen=True, slots=True)
class OpenCaseCommand:
    """Input from shipment.late_detected / shipment.lost_detected (inbox) or POST /cases/report."""

    order_id: UUID
    kind: CaseKind
    origin: CaseOrigin
    source_event_id: (
        UUID | None
    )  # inbox event_id for detector origin; None for buyer report
    untrusted_text: (
        str | None
    )  # buyer report only; length-capped by PS_RESOLUTION_CASE_REPORT_MAX_CHARS


@dataclass(frozen=True, slots=True)
class OpenedCase:
    """Result of open_case. created=False means the (order_id, kind) case already existed (no duplicate)."""

    case_id: UUID
    state: CaseState
    created: bool
    terms_snapshot: TermsSnapshot | None
    window_hold: bool


async def open_case(session: AsyncSession, cmd: OpenCaseCommand) -> OpenedCase:
    """Create the case for (order_id, kind) if missing, back-fill PROTECTED -> MONITORING -> PROBLEM_DETECTED.

    Inputs: command and an open transaction. Reads mandate terms (sync) BEFORE the transaction
    and freezes them into terms_snapshot + terms_hash (spec s2, C6).
    Output: OpenedCase.
    Edge cases: duplicate (order_id, kind) -> created=False, no new rows (spec s13 unique constraint);
    mandate unreachable OR revoked/expired/exhausted -> still opens the case, terms_snapshot=None
    so decide() fails closed (D0) -- see clients.get_mandate_terms for the revoke-blocks-new-
    protection rule (api.md s6, confirmed D1);
    case.opened_at uses the demo clock from the event (spec s10).
    """
    existing = await repo.get_case_by_order_and_kind(
        session, str(cmd.order_id), cmd.kind.value
    )
    if existing is not None:
        return OpenedCase(
            case_id=existing["id"],
            state=CaseState(existing["state"]),
            created=False,
            terms_snapshot=None,
            window_hold=existing["window_hold"],
        )

    # Order identity (mandate_id, capture_id, buyer_id) is server-derived from checkout, never
    # the client (spec s2). Mandate terms are then read BEFORE the transaction and frozen into
    # terms_snapshot + terms_hash (spec s2, C6). Unreachable mandate/checkout still opens the
    # case so decide() fails closed later (D0) rather than blocking case materialization.
    mandate_id, capture_id, buyer_id = await clients.get_order_identity(
        str(cmd.order_id)
    )
    terms: TermsSnapshot | None = None
    terms_hash: str | None = None
    if mandate_id is not None:
        terms, terms_hash, _hmac_valid = await clients.get_mandate_terms(mandate_id)

    case_id = uuid4()
    opened_at = now_utc()
    terms_dict = (
        {
            "kinds_covered": sorted(k.value for k in terms.kinds_covered),
            "max_refund_minor": terms.max_refund_minor,
            "window_hold_days": terms.window_hold_days,
            "rule": terms.rule,
        }
        if terms is not None
        else None
    )

    await repo.insert_case(
        session,
        case_id=case_id,
        order_id=str(cmd.order_id),
        capture_id=capture_id,
        mandate_id=mandate_id,
        buyer_id=buyer_id,
        kind=cmd.kind.value,
        origin=cmd.origin.value,
        state=CaseState.PROBLEM_DETECTED.value,
        terms_snapshot=terms_dict,
        terms_hash=terms_hash,
        opened_at=opened_at,
        window_hold=True,
        untrusted_text=cmd.untrusted_text,
    )

    # Lazy materialization: back-fill PROTECTED -> MONITORING -> PROBLEM_DETECTED in one
    # transaction (spec s3), actor=system, reason=materialized. The row above is created
    # already in PROBLEM_DETECTED, so the back-fill is purely the audit trail (T1, T2 or T3).
    await repo.insert_case_transition(
        session,
        case_id=case_id,
        from_state=None,
        to_state=CaseState.PROTECTED.value,
        actor=Actor.SYSTEM.value,
        reason="materialized",
    )
    await repo.insert_case_transition(
        session,
        case_id=case_id,
        from_state=CaseState.PROTECTED.value,
        to_state=CaseState.MONITORING.value,
        actor=Actor.SYSTEM.value,
        reason="materialized",
    )
    transition_id = "T2" if cmd.origin == CaseOrigin.BUYER_REPORT else "T3"
    await repo.insert_case_transition(
        session,
        case_id=case_id,
        from_state=CaseState.MONITORING.value,
        to_state=CaseState.PROBLEM_DETECTED.value,
        actor=Actor.SYSTEM.value,
        reason=transition_id,
    )

    await repo.insert_outbox_event(
        session,
        event_id=uuid4(),
        event_type="case.state_changed",
        aggregate_id=str(case_id),
        payload={
            "case_id": str(case_id),
            "transition_id": transition_id,
            "from_state": CaseState.MONITORING.value,
            "to_state": CaseState.PROBLEM_DETECTED.value,
            "version": 0,
            "reason_code": None,
        },
    )

    return OpenedCase(
        case_id=case_id,
        state=CaseState.PROBLEM_DETECTED,
        created=True,
        terms_snapshot=terms,
        window_hold=True,
    )
