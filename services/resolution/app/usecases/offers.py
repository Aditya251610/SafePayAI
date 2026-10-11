"""Offer use cases: create an offer/proposal inside terms, accept it (single winner), and compute its hash.

Implements resolution/spec.md section 5 (proposal_hash, tiers), section 3 T7/T9/T11 (offer created,
accepted, declined) and api.md POST /offers/{id}/accept and /decline. Accept is a conditional
single-row UPDATE (rowcount 1 wins); a loser gets the existing result, not an error (spec s13). Scaffold only.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app import repo
from app.domain.policy import Decision, PolicyClass
from app.domain.proposal import (
    Action,
    ApprovalTier,
    OfferRecord,
    OfferStatus,
    ProposalFields,
    hashes_match,
    proposal_hash,
)
from app.domain.states import Actor, CaseState
from app.usecases.transitions import TransitionRequest, apply_transition


@dataclass(frozen=True, slots=True)
class AcceptResult:
    """Response core of POST /offers/{id}/accept (api.md 200 body, service side)."""

    case_id: UUID
    state: str  # CaseState value after accept (APPROVED / REFUNDING / RESOLVED_*)
    replayed: bool  # True when this call lost the race or repeated an accept (returns existing result)


async def create_offer(
    session: AsyncSession,
    case_id: UUID,
    decision: Decision,
    action: Action,
    tier: ApprovalTier,
) -> OfferRecord:
    """Persist an offer for a case from a Decision (T7), with proposal_hash and offer_seq.

    Inputs: case id, the Decision (amount/currency come from it, server-side only), action, tier.
    Output: OfferRecord with status ACTIVE. Writes offers row + offer.created outbox in one tx.
    Edge cases: decision class HUMAN_REVIEW must never create an offer (spec s4, T8); the offer is
    immutable after creation (spec s5); a new offer_seq supersedes the previous one (T26).
    """
    if decision.klass == PolicyClass.HUMAN_REVIEW:
        raise ValueError(
            "HUMAN_REVIEW decisions must never create an offer (spec s4, T8)"
        )
    if decision.amount_minor is None or decision.currency is None:
        raise ValueError("decision has no derived amount; cannot create an offer")

    case = await repo.get_case(session, case_id)
    if case is None:
        raise ValueError(f"case {case_id} not found")

    offer_seq = await repo.get_next_offer_seq(session, case_id)
    offer_id = uuid4()
    fields = ProposalFields(
        case_id=case_id,
        order_id=case["order_id"],
        capture_id=case.get("capture_id") or "",
        mandate_id=case.get("mandate_id") or "",
        terms_hash=case.get("terms_hash") or "",
        policy_version=decision.policy_version,
        action=action,
        amount_minor=decision.amount_minor,
        currency=decision.currency,
        offer_seq=offer_seq,
    )
    p_hash = proposal_hash(fields)

    await repo.insert_offer(
        session,
        offer_id=offer_id,
        case_id=case_id,
        offer_seq=offer_seq,
        action=action.value,
        amount_minor=decision.amount_minor,
        currency=decision.currency,
        tier=tier.value,
        proposal_hash=p_hash,
        expires_at=None,
    )
    await repo.insert_outbox_event(
        session,
        event_id=uuid4(),
        event_type="offer.created",
        aggregate_id=str(case_id),
        payload={
            "case_id": str(case_id),
            "offer_id": str(offer_id),
            "offer_seq": offer_seq,
            "action": action.value,
            "amount_minor": decision.amount_minor,
            "currency": decision.currency,
            "tier": tier.value,
            "proposal_hash": p_hash,
        },
    )

    # T7 (spec s3): TRIAGED -> OFFERED, only on the first offer for a case (offer_seq == 1).
    # A later offer (merchant override, T25/T26) supersedes an already-OFFERED case instead.
    if CaseState(case["state"]) == CaseState.TRIAGED and offer_seq == 1:
        await apply_transition(
            session,
            TransitionRequest(
                case_id=case_id,
                expected_from=CaseState.TRIAGED,
                to_state=CaseState.OFFERED,
                expected_version=case["version"],
                transition_id="T7",
                actor=Actor.SYSTEM,
                reason_code=None,
            ),
        )

    return OfferRecord(
        offer_id=offer_id,
        case_id=case_id,
        offer_seq=offer_seq,
        action=action,
        amount_minor=decision.amount_minor,
        currency=decision.currency,
        tier=tier,
        status=OfferStatus.ACTIVE,
        proposal_hash=p_hash,
        terms_hash=case.get("terms_hash") or "",
        policy_version=decision.policy_version,
    )


async def accept_offer(
    session: AsyncSession,
    offer_id: UUID,
    buyer_id: str,
    proposal_hash_from_client: str,
) -> AcceptResult:
    """Buyer accepts an ACTIVE offer (T9, tier 1): hash must match, buyer must own the case.

    Inputs: offer id, authenticated buyer id (from token only), proposal_hash echoed by the client.
    Output: AcceptResult. Single winner via conditional UPDATE offers ... WHERE status = 'ACTIVE'.
    Edge cases: wrong owner -> 404 (no enumeration, api s1); superseded/expired -> 409 OFFER_NOT_ACTIVE;
    hash mismatch -> 409 PROPOSAL_HASH_MISMATCH; repeat accept -> replayed=True, same result.
    Execution (checks 1-9) runs after this returns; a frozen switch leaves the case APPROVED (spec s9).
    """
    offer = await repo.get_offer(session, offer_id)
    if offer is None:
        raise LookupError("OFFER_NOT_FOUND")

    case = await repo.get_case_for_update(session, offer["case_id"])
    if case is None or case.get("buyer_id") != buyer_id:
        raise LookupError("OFFER_NOT_FOUND")  # no enumeration (api s1)

    if offer["status"] == "ACCEPTED":
        return AcceptResult(case_id=case["id"], state=case["state"], replayed=True)
    if offer["status"] != "ACTIVE":
        raise ValueError("OFFER_NOT_ACTIVE")
    if not hashes_match(offer["proposal_hash"], proposal_hash_from_client):
        raise ValueError("PROPOSAL_HASH_MISMATCH")

    won = await repo.cas_accept_offer(session, offer_id)
    if not won:
        # Lost the race: someone else already accepted/superseded it.
        refreshed = await repo.get_offer(session, offer_id)
        if refreshed and refreshed["status"] == "ACCEPTED":
            return AcceptResult(case_id=case["id"], state=case["state"], replayed=True)
        raise ValueError("OFFER_NOT_ACTIVE")

    outcome = await apply_transition(
        session,
        TransitionRequest(
            case_id=case["id"],
            expected_from=CaseState(case["state"]),
            to_state=CaseState.APPROVED,
            expected_version=case["version"],
            transition_id="T9",
            actor=Actor.BUYER,
            reason_code=None,
        ),
    )

    return AcceptResult(case_id=case["id"], state=outcome.state.value, replayed=False)


async def decline_offer(
    session: AsyncSession,
    offer_id: UUID,
    buyer_id: str,
    reason_code: str,
) -> None:
    """Buyer declines an ACTIVE offer (T11) with an enum reason code.

    Inputs: offer id, buyer id from token, reason enum (NOT_WANTED | WANT_HUMAN | OTHER per api s3.6).
    Output: None; the case moves to DECLINED.
    Edge cases: wrong owner -> 404; non-active offer -> 409; reason outside the enum -> 422.
    """
    valid_reasons = {"NOT_WANTED", "WANT_HUMAN", "OTHER"}
    if reason_code not in valid_reasons:
        raise ValueError("INVALID_REASON_CODE")

    offer = await repo.get_offer(session, offer_id)
    if offer is None:
        raise LookupError("OFFER_NOT_FOUND")
    case = await repo.get_case_for_update(session, offer["case_id"])
    if case is None or case.get("buyer_id") != buyer_id:
        raise LookupError("OFFER_NOT_FOUND")
    if offer["status"] != "ACTIVE":
        raise ValueError("OFFER_NOT_ACTIVE")

    declined = await repo.cas_decline_offer(session, offer_id)
    if not declined:
        raise ValueError("OFFER_NOT_ACTIVE")

    await apply_transition(
        session,
        TransitionRequest(
            case_id=case["id"],
            expected_from=CaseState(case["state"]),
            to_state=CaseState.DECLINED,
            expected_version=case["version"],
            transition_id="T11",
            actor=Actor.BUYER,
            reason_code=None,
        ),
    )


def offer_is_usable(offer: OfferRecord, now_is_before_expiry: bool) -> bool:
    """Return True if an offer may still be accepted: status ACTIVE and not expired.

    Inputs: the offer and a precomputed boolean (caller compares expires_at with the demo clock).
    Output: bool. Edge cases: expired -> caller moves case to HUMAN_REVIEW via T12, never denies (spec s10).
    """
    return offer.status == OfferStatus.ACTIVE and now_is_before_expiry
