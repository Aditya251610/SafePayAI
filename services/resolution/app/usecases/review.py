"""Shared conservative-override helper for the reviewer and merchant-override exception paths.

Both POST /cases/{id}/review-decision (PROPOSE_REFUND/PROPOSE_RESHIP, T13) and
POST /cases/{id}/merchant-action (OVERRIDE_OFFER, T25/T26) need a Decision to hand to
usecases.offers.create_offer, but create_offer refuses a HUMAN_REVIEW klass (spec s4, T8) --
by construction, reviewer/merchant decisions ARE the human-in-the-loop override for exactly the
cases where decide() still says HUMAN_REVIEW (that is the whole point of a human in the loop).
This module derives a conservative amount in that case -- never a client-supplied number
(CLAUDE.md money rule) -- capped at the mandate's own terms_snapshot.max_refund_minor and never
above the capture's own remaining refundable amount (the same capture facts
assemble_facts_and_decide already reads), then wraps that into a Decision with klass
OUTSIDE_TERMS: the honest label for an out-of-policy exception a human explicitly approved.
PolicyClass.MERCHANT_OVERRIDE already exists but spec s4 documents it as "set by the
merchant-action path, not by decide()" -- reusing OUTSIDE_TERMS here keeps create_offer's one
existing guard clause (klass != HUMAN_REVIEW) sufficient without widening PolicyClass for a
single internal code path.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app import clients, repo
from app.domain.policy import Decision, PolicyClass, PolicyConfig
from app.usecases.decide import assemble_facts_and_decide


async def decide_with_override(
    session: AsyncSession, case_id: UUID, cfg: PolicyConfig
) -> Decision:
    """Fresh decide(); if it still says HUMAN_REVIEW, return a conservative OUTSIDE_TERMS
    Decision capped at terms_snapshot.max_refund_minor (and the capture's own remaining
    refundable amount) instead.

    Inputs: case id and policy config (same as assemble_facts_and_decide).
    Output: a Decision whose klass is never HUMAN_REVIEW and whose amount_minor/currency are
    never None, suitable for usecases.offers.create_offer.
    Edge cases: raises ValueError("NO_REFUNDABLE_AMOUNT") if neither the terms cap nor the
    capture's remaining amount is a usable positive number -- caller maps that to 409.
    """
    decision = await assemble_facts_and_decide(session, case_id, cfg)
    if decision.klass != PolicyClass.HUMAN_REVIEW:
        return decision

    case = await repo.get_case(session, case_id)
    if case is None:
        raise ValueError(f"case {case_id} not found")

    terms_snapshot = case.get("terms_snapshot") or {}
    cap_minor = int(terms_snapshot.get("max_refund_minor") or 0)

    capture = (
        await clients.get_capture_facts(case["order_id"])
        if case.get("order_id")
        else None
    )
    remaining_minor = (
        capture.amount_minor - capture.refunded_total_minor if capture else None
    )
    currency = (capture.currency if capture else None) or case.get("currency") or "USD"

    candidates = [v for v in (cap_minor, remaining_minor) if v and v > 0]
    if not candidates:
        raise ValueError("NO_REFUNDABLE_AMOUNT")
    amount_minor = min(candidates)

    return Decision(
        klass=PolicyClass.OUTSIDE_TERMS,
        reasons=decision.reasons,
        amount_minor=amount_minor,
        currency=currency,
        policy_version=decision.policy_version,
        facts_hash=decision.facts_hash,
    )
