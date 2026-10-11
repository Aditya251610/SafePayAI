"""Decide use case: assemble fresh DecisionFacts from sync reads, call the pure decide(), persist the Decision.

Implements resolution/spec.md section 4 (facts are assembled by the use case from fresh sync reads
and then frozen; decide() is pure) and transitions T7/T8 (TRIAGED -> OFFERED or HUMAN_REVIEW).
Port calls (triage, mandate, tracking, checkout) are your adapters; this file only orchestrates. Scaffold only.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app import clients, repo
from app.domain.policy import (
    CaptureFacts,
    Decision,
    DecisionFacts,
    PolicyClass,
    PolicyConfig,
    ReasonCode,
    TermsSnapshot,
    decide,
)
from app.domain.states import Actor, CaseKind, CaseState
from app.usecases.transitions import TransitionRequest, apply_transition


async def assemble_facts_and_decide(
    session: AsyncSession,
    case_id: UUID,
    cfg: PolicyConfig,
) -> Decision:
    """Read fresh facts for the case (triage, terms, tracking, capture, buyer velocity), then decide().

    Inputs: case id, pinned PolicyConfig for this decision.
    Output: Decision, also persisted to policy_decisions with the facts hash.
    Edge cases: any port error, timeout or missing fact -> that fact is None so decide() returns
    HUMAN_REVIEW (fail closed, spec s4 D0). Never call an LLM here; triage is read from the case row.
    """
    case = await repo.get_case(session, case_id)
    if case is None:
        raise ValueError(f"case {case_id} not found")

    kind = CaseKind(case["kind"])
    now = repo.now_utc()

    terms: TermsSnapshot | None = None
    terms_snapshot_raw = case.get("terms_snapshot")
    if terms_snapshot_raw:
        terms = TermsSnapshot(
            kinds_covered=frozenset(
                CaseKind(k) for k in terms_snapshot_raw.get("kinds_covered", [])
            ),
            max_refund_minor=int(terms_snapshot_raw.get("max_refund_minor", 0)),
            window_hold_days=int(terms_snapshot_raw.get("window_hold_days", 0)),
            rule=str(terms_snapshot_raw.get("rule", "")),
        )

    mandate_hash_valid = terms is not None
    protected_until: datetime | None = None
    if case.get("mandate_id") and case.get("order_id"):
        protected_until_raw = await clients.get_protected_until(case["order_id"])
        if isinstance(protected_until_raw, str):
            try:
                protected_until = datetime.fromisoformat(protected_until_raw)
            except ValueError:
                protected_until = None
        elif isinstance(protected_until_raw, datetime):
            protected_until = protected_until_raw

    capture: CaptureFacts | None = None
    if case.get("order_id"):
        capture = await clients.get_capture_facts(case["order_id"])

    carrier_agrees: bool | None = None
    carrier_status: str | None = None
    if case.get("order_id"):
        tracking_facts = await clients.get_tracking_agreement(case["order_id"], kind)
        carrier_agrees = tracking_facts.carrier_agrees
        carrier_status = tracking_facts.carrier_status

    triage_body = await clients.classify_triage(
        case["order_id"], case.get("untrusted_text")
    )
    if triage_body is not None:
        triage_ok = bool(triage_body.get("ok", False))
        triage_confidence = float(triage_body.get("confidence", 0.0))
        injection_suspected = bool(triage_body.get("injection_suspected", False))
    elif case["origin"] == "DETECTOR":
        # spec s3 T5: detector origin (kind already known) does not need triage-ai.
        triage_ok = True
        triage_confidence = 1.0
        injection_suspected = False
    else:
        # triage-ai unreachable/not built -> fail closed (spec s4 D1).
        triage_ok = False
        triage_confidence = 0.0
        injection_suspected = False

    buyer_completed_refunds_in_window: int | None = None
    if case.get("buyer_id"):
        from datetime import timedelta

        window_start = now - timedelta(days=cfg.velocity_window_days)
        buyer_completed_refunds_in_window = (
            await repo.count_buyer_completed_refunds_in_window(
                session, case["buyer_id"], window_start
            )
        )

    facts = DecisionFacts(
        kind=kind,
        triage_ok=triage_ok,
        triage_confidence=triage_confidence,
        injection_suspected=injection_suspected,
        carrier_status=carrier_status,
        carrier_agrees=carrier_agrees,
        terms=terms,
        mandate_hash_valid=mandate_hash_valid,
        protected_until=protected_until,
        case_opened_at=case["opened_at"],
        now=now,
        capture=capture,
        item_categories=frozenset(),
        buyer_completed_refunds_in_window=buyer_completed_refunds_in_window,
    )

    decision = decide(facts, cfg)

    await repo.insert_policy_decision(
        session,
        case_id=case_id,
        klass=decision.klass.value,
        policy_version=decision.policy_version,
        reasons=[r.code.value for r in decision.reasons],
        facts_hash=decision.facts_hash,
    )

    # Drive T5/T6/T7/T8 (spec s3) only on the first pass out of PROBLEM_DETECTED. Re-evaluation
    # calls (e.g. check 6 in execute_refund.run_checks, which re-runs decide() on an already
    # APPROVED/REFUNDING case) must NOT transition the case - they only compare klass.
    if CaseState(case["state"]) == CaseState.PROBLEM_DETECTED:
        triage_failed_closed = decision.reasons and decision.reasons[0].code in (
            ReasonCode.FACT_UNAVAILABLE,
            ReasonCode.TERMS_INVALID,
            ReasonCode.UNSUPPORTED_TERMS,
            ReasonCode.TRIAGE_FAIL_CLOSED,
        )
        if triage_failed_closed:
            await apply_transition(
                session,
                TransitionRequest(
                    case_id=case_id,
                    expected_from=CaseState.PROBLEM_DETECTED,
                    to_state=CaseState.HUMAN_REVIEW,
                    expected_version=case["version"],
                    transition_id="T6",
                    actor=Actor.SYSTEM,
                    reason_code=decision.reasons[0].code,
                ),
            )
        else:
            triaged = await apply_transition(
                session,
                TransitionRequest(
                    case_id=case_id,
                    expected_from=CaseState.PROBLEM_DETECTED,
                    to_state=CaseState.TRIAGED,
                    expected_version=case["version"],
                    transition_id="T5",
                    actor=Actor.SYSTEM,
                    reason_code=None,
                ),
            )
            if decision.klass == PolicyClass.HUMAN_REVIEW:
                await apply_transition(
                    session,
                    TransitionRequest(
                        case_id=case_id,
                        expected_from=CaseState.TRIAGED,
                        to_state=CaseState.HUMAN_REVIEW,
                        expected_version=triaged.version,
                        transition_id="T8",
                        actor=Actor.SYSTEM,
                        reason_code=decision.reasons[0].code
                        if decision.reasons
                        else None,
                    ),
                )
            # INSIDE_TERMS/OUTSIDE_TERMS stay TRIAGED; create_offer drives T7 (TRIAGED -> OFFERED).

    return decision
