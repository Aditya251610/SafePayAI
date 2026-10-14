"""Decide use case: assemble fresh DecisionFacts from sync reads, call the pure decide(), persist the Decision.

Implements resolution/spec.md section 4 (facts are assembled by the use case from fresh sync reads
and then frozen; decide() is pure) and transitions T7/T8 (TRIAGED -> OFFERED or HUMAN_REVIEW).
Port calls (triage, mandate, tracking, checkout) are your adapters; this file only orchestrates. Scaffold only.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

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

# tracking's own ShipmentStatus vocabulary -> triage-ai's ShipStatus contract
# (services/triage-ai/app/schemas/triage.py) -- the two services were built
# independently and never agreed on one enum; this is the one place that maps
# between them, kept here (not in clients.py) per this module's existing
# "business logic stays in the usecase" convention.
_TRACKING_TO_TRIAGE_STATUS = {
    "LABEL_CREATED": "LABEL_CREATED",
    "IN_TRANSIT": "IN_TRANSIT",
    "OUT_FOR_DELIVERY": "IN_TRANSIT",
    "EXCEPTION": "DELAYED",
    "LOST": "LOST_FLAGGED",
    "DELIVERED": "DELIVERED",
    "CANCELLED": "UNKNOWN",
}


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
    if case.get("mandate_id") and case.get("order_id") and terms is not None:
        protected_until_raw = await clients.get_protected_until(
            case["order_id"], terms.window_hold_days
        )
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
    tracking_facts: clients.TrackingFacts | None = None
    if case.get("order_id"):
        tracking_facts = await clients.get_tracking_agreement(case["order_id"], kind)
        carrier_agrees = tracking_facts.carrier_agrees
        carrier_status = tracking_facts.carrier_status

    # Assemble triage-ai's real ClassifyRequest shape (order/timeline facts), per
    # services/triage-ai/app/schemas/triage.py. Business logic (this assembly) stays in
    # resolution's own usecase, not in libs/common or the thin clients.py adapter.
    order_date = case["opened_at"].date()  # fallback proxy if checkout is unreachable
    order_state_raw: str | None = None
    if case.get("order_id"):
        order_state_facts = await clients.get_order_state_facts(case["order_id"])
        if order_state_facts is not None:
            order_date = order_state_facts.created_at.date()
            order_state_raw = order_state_facts.status
    order_facts_payload = {
        "order_ref": case["order_id"] or str(case_id),
        "order_date": order_date.isoformat(),
        "promised_by": protected_until.date().isoformat() if protected_until else None,
        "demo_now": now.isoformat(),
        "state": order_state_raw or (capture.status if capture else "UNKNOWN"),
        # checkout's GET /orders/{id} does not expose line-item titles today (known gap,
        # see this module's clients.py docstring) -- empty list, which the schema defaults to.
        "item_titles": [],
        "amount_minor": capture.amount_minor if capture else None,
        "currency": capture.currency if capture else None,
    }
    # Tracking's GET /shipments/{order_id} now exposes a real per-event "events" list
    # (its own ShipmentStatus vocabulary) alongside the aggregate `consistency`
    # summary; map it into triage-ai's exact TimelineEvent contract here, in the
    # usecase, same as this module's own convention of keeping that translation out
    # of the thin clients.py adapter and out of libs/common.
    timeline_payload = [
        {
            "event_id": f"se-{i}",
            "ts": e.get("occurred_at_sim"),
            "status": _TRACKING_TO_TRIAGE_STATUS.get(str(e.get("status")), "UNKNOWN"),
            "note": e.get("note_code"),
        }
        for i, e in enumerate(tracking_facts.events if tracking_facts else [])
    ]
    triage_origin = "buyer_report" if case["origin"] == "BUYER_REPORT" else "detector"

    triage_result = await clients.classify_triage(
        case_id=case_id,
        trace_id=str(uuid4()),
        origin=triage_origin,
        buyer_text=case.get("untrusted_text"),
        timeline=timeline_payload,
        order=order_facts_payload,
    )
    if triage_result is not None:
        triage_ok = triage_result.route == "PROCEED"
        triage_confidence = triage_result.confidence
        injection_suspected = triage_result.injection_suspected
    elif case["origin"] == "DETECTOR":
        # spec s3 T5: detector origin (kind already known) does not need triage-ai.
        triage_ok = True
        triage_confidence = 1.0
        injection_suspected = False
    else:
        # triage-ai unreachable/malformed -> fail closed (spec s4 D1).
        triage_ok = False
        triage_confidence = 0.0
        injection_suspected = False

    # Reclassify case.kind from triage's answer for BUYER_REPORT-origin cases ONLY (DETECTOR
    # cases already know their kind for certain and must not be overridden). Only on the
    # FIRST pass out of PROBLEM_DETECTED (mirrors the T5/T6/T7/T8 guard below) so a
    # re-evaluation call (e.g. execute_refund's re-check) never flip-flops kind. Guarded
    # against the (order_id, kind) unique constraint: if a case already exists for this
    # order under triage's proposed kind (e.g. a DETECTOR case for the same order/kind),
    # skip the reclassification rather than risk an IntegrityError mid-transaction -- a
    # rare collision, left as OTHER rather than crashing the decide path.
    if (
        case["origin"] == "BUYER_REPORT"
        and triage_result is not None
        and triage_result.category != kind
        and case["kind"] == CaseKind.OTHER.value
        and CaseState(case["state"]) == CaseState.PROBLEM_DETECTED
    ):
        collision = await repo.get_case_by_order_and_kind(
            session, case["order_id"], triage_result.category.value
        )
        if collision is None:
            kind = triage_result.category
            await repo.update_case_kind(session, case_id, kind.value)

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
