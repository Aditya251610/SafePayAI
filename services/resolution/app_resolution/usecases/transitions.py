"""The only case-mutation path: apply_transition, with CAS on version and one tx for row + history + outbox.

Implements resolution/spec.md section 3 (every transition: UPDATE cases ... WHERE state = :from AND
version = :v; rowcount 0 -> ConcurrentModification; case_transitions row and outbox row in the same
transaction) and section 13 (row locks, CAS). Scaffold only.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app_resolution import repo
from app_resolution.domain.policy import ReasonCode
from app_resolution.domain.states import (
    Actor,
    CaseState,
    ConcurrentModification,
    IllegalTransition,
    is_legal_transition,
)


@dataclass(frozen=True, slots=True)
class TransitionRequest:
    """Input to apply_transition. Never carries money fields (spec s3, api s1 FIELD_NOT_ALLOWED)."""

    case_id: UUID
    expected_from: CaseState
    to_state: CaseState
    expected_version: int
    transition_id: str  # "T1".."T27" from TRANSITIONS
    actor: Actor
    reason_code: ReasonCode | None


@dataclass(frozen=True, slots=True)
class TransitionOutcome:
    """Result after a successful CAS update."""

    case_id: UUID
    state: CaseState
    version: int


async def apply_transition(
    session: AsyncSession, req: TransitionRequest
) -> TransitionOutcome:
    """Validate against LEGAL_TRANSITIONS, CAS-update cases, insert case_transitions and outbox rows.

    Inputs: TransitionRequest and an open transaction (caller holds SELECT ... FOR UPDATE where needed).
    Output: TransitionOutcome with the new state and version.
    Edge cases: illegal edge -> IllegalTransition (409 ILLEGAL_TRANSITION); rowcount 0 ->
    ConcurrentModification (409 CONCURRENT_MODIFICATION); emits case.state_changed in the same tx (spec C5).
    """
    if not is_legal_transition(req.expected_from, req.to_state):
        raise IllegalTransition(
            f"{req.expected_from} -> {req.to_state} is not legal ({req.transition_id})"
        )

    updated = await repo.cas_case_state(
        session,
        case_id=req.case_id,
        expected_state=req.expected_from.value,
        expected_version=req.expected_version,
        new_state=req.to_state.value,
    )
    if not updated:
        raise ConcurrentModification(
            f"case {req.case_id} version/state changed under us"
        )

    await repo.insert_case_transition(
        session,
        case_id=req.case_id,
        from_state=req.expected_from.value,
        to_state=req.to_state.value,
        actor=req.actor.value,
        reason=req.reason_code.value if req.reason_code else None,
    )

    new_version = req.expected_version + 1
    await repo.insert_outbox_event(
        session,
        event_id=uuid4(),
        event_type="case.state_changed",
        aggregate_id=str(req.case_id),
        payload={
            "case_id": str(req.case_id),
            "transition_id": req.transition_id,
            "from_state": req.expected_from.value,
            "to_state": req.to_state.value,
            "version": new_version,
            "reason_code": req.reason_code.value if req.reason_code else None,
        },
    )

    return TransitionOutcome(
        case_id=req.case_id, state=req.to_state, version=new_version
    )
