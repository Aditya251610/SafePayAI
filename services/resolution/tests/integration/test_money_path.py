"""Integration tests against a real throwaway Postgres: lazy case materialization, the CAS
transition path, the policy decision fail-closed path, and the full INSIDE_TERMS
report -> decide -> offer -> accept -> refund saga (money path). mandate/checkout/tracking/
paypal-adapter are mocked via monkeypatch on app.clients (no real HTTP calls, real DB underneath).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app import clients, repo
from app.domain.policy import CaptureFacts, PolicyClass, PolicyConfig, TermsSnapshot
from app.domain.proposal import Action, ApprovalTier
from app.domain.states import Actor, CaseKind, CaseOrigin, CaseState, IllegalTransition
from app.usecases.decide import assemble_facts_and_decide
from app.usecases.execute_refund import execute_refund
from app.usecases.offers import accept_offer, create_offer
from app.usecases.open_case import OpenCaseCommand, open_case
from app.usecases.transitions import TransitionRequest, apply_transition

CFG = PolicyConfig(
    policy_version="v1",
    refund_cap_minor=5000,
    excluded_categories=frozenset(),
    velocity_max=2,
    velocity_window_days=30,
    triage_min_confidence=0.7,
)


async def test_open_case_lazy_materialization_backfills_transitions(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_identity(order_id: str, token: str | None = None):
        return None, None, None  # mandate/checkout unreachable

    async def fake_terms(mandate_id: str, token: str | None = None):
        return None, None, False

    monkeypatch.setattr(clients, "get_order_identity", fake_identity)
    monkeypatch.setattr(clients, "get_mandate_terms", fake_terms)

    order_id = uuid4()
    opened = await open_case(
        session,
        OpenCaseCommand(
            order_id=order_id,
            kind=CaseKind.LATE,
            origin=CaseOrigin.DETECTOR,
            source_event_id=None,
            untrusted_text=None,
        ),
    )
    await session.commit()

    assert opened.created is True
    assert opened.state == CaseState.PROBLEM_DETECTED
    assert (
        opened.terms_snapshot is None
    )  # mandate unreachable -> decide() fails closed later (D0)

    transitions = await session.execute(
        __import__("sqlalchemy").text(
            "SELECT reason, to_state FROM resolution.case_transitions "
            "WHERE case_id = :id ORDER BY ctid"
        ),
        {"id": opened.case_id},
    )
    rows = transitions.all()
    assert [r[1] for r in rows] == ["PROTECTED", "MONITORING", "PROBLEM_DETECTED"]


async def test_open_case_is_idempotent_for_same_order_and_kind(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_identity(order_id: str, token: str | None = None):
        return None, None, None

    async def fake_terms(mandate_id: str, token: str | None = None):
        return None, None, False

    monkeypatch.setattr(clients, "get_order_identity", fake_identity)
    monkeypatch.setattr(clients, "get_mandate_terms", fake_terms)

    order_id = uuid4()
    cmd = OpenCaseCommand(
        order_id=order_id,
        kind=CaseKind.LOST,
        origin=CaseOrigin.DETECTOR,
        source_event_id=None,
        untrusted_text=None,
    )
    first = await open_case(session, cmd)
    await session.commit()
    second = await open_case(session, cmd)

    assert first.created is True
    assert second.created is False
    assert second.case_id == first.case_id


async def test_apply_transition_rejects_illegal_edge(session: AsyncSession) -> None:
    case_id = uuid4()
    await repo.insert_case(
        session,
        case_id=case_id,
        order_id=str(uuid4()),
        capture_id=None,
        mandate_id=None,
        buyer_id=None,
        kind=CaseKind.LATE.value,
        origin=CaseOrigin.DETECTOR.value,
        state=CaseState.PROTECTED.value,
        terms_snapshot=None,
        terms_hash=None,
        opened_at=datetime.now(UTC),
        window_hold=False,
        untrusted_text=None,
    )
    await session.commit()

    with pytest.raises(IllegalTransition):
        await apply_transition(
            session,
            TransitionRequest(
                case_id=case_id,
                expected_from=CaseState.PROTECTED,
                to_state=CaseState.APPROVED,
                expected_version=0,
                transition_id="T-ILLEGAL",
                actor=Actor.SYSTEM,
                reason_code=None,
            ),
        )


async def test_apply_transition_cas_mismatch_raises(session: AsyncSession) -> None:
    from app.domain.states import ConcurrentModification

    case_id = uuid4()
    await repo.insert_case(
        session,
        case_id=case_id,
        order_id=str(uuid4()),
        capture_id=None,
        mandate_id=None,
        buyer_id=None,
        kind=CaseKind.LATE.value,
        origin=CaseOrigin.DETECTOR.value,
        state=CaseState.PROTECTED.value,
        terms_snapshot=None,
        terms_hash=None,
        opened_at=datetime.now(UTC),
        window_hold=False,
        untrusted_text=None,
    )
    await session.commit()

    with pytest.raises(ConcurrentModification):
        await apply_transition(
            session,
            TransitionRequest(
                case_id=case_id,
                expected_from=CaseState.PROTECTED,
                to_state=CaseState.MONITORING,
                expected_version=99,  # wrong version
                transition_id="T1",
                actor=Actor.SYSTEM,
                reason_code=None,
            ),
        )


def _mock_money_path(
    monkeypatch: pytest.MonkeyPatch,
    *,
    mandate_id: str,
    capture_id: str,
    buyer_id: str,
    amount_minor: int = 2000,
) -> None:
    async def fake_identity(order_id: str, token: str | None = None):
        return mandate_id, capture_id, buyer_id

    async def fake_terms(mid: str, token: str | None = None):
        terms = TermsSnapshot(
            kinds_covered=frozenset({CaseKind.LATE, CaseKind.LOST}),
            max_refund_minor=10000,
            window_hold_days=30,
            rule="FULL_ORDER",
        )
        return terms, "terms-hash-1", True

    async def fake_protected_until(order_id: str, token: str | None = None):
        return (datetime.now(UTC) + timedelta(days=30)).isoformat()

    async def fake_capture(order_id: str, token: str | None = None):
        return CaptureFacts(
            capture_id=capture_id,
            status="COMPLETED",
            amount_minor=amount_minor,
            refunded_total_minor=0,
            currency="USD",
        )

    async def fake_tracking(order_id: str, kind: CaseKind, token: str | None = None):
        return clients.TrackingFacts(carrier_status="IN_TRANSIT", carrier_agrees=True)

    async def fake_triage(**kwargs):
        return None

    monkeypatch.setattr(clients, "get_order_identity", fake_identity)
    monkeypatch.setattr(clients, "get_mandate_terms", fake_terms)
    monkeypatch.setattr(clients, "get_protected_until", fake_protected_until)
    monkeypatch.setattr(clients, "get_capture_facts", fake_capture)
    monkeypatch.setattr(clients, "get_tracking_agreement", fake_tracking)
    monkeypatch.setattr(clients, "classify_triage", fake_triage)


async def test_decide_fails_closed_when_mandate_unreachable(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_identity(order_id: str, token: str | None = None):
        return None, None, None

    async def fake_terms(mid: str, token: str | None = None):
        return None, None, False

    monkeypatch.setattr(clients, "get_order_identity", fake_identity)
    monkeypatch.setattr(clients, "get_mandate_terms", fake_terms)

    opened = await open_case(
        session,
        OpenCaseCommand(
            order_id=uuid4(),
            kind=CaseKind.LATE,
            origin=CaseOrigin.DETECTOR,
            source_event_id=None,
            untrusted_text=None,
        ),
    )
    await session.commit()

    decision = await assemble_facts_and_decide(session, opened.case_id, CFG)
    assert decision.klass == PolicyClass.HUMAN_REVIEW


async def test_full_inside_terms_money_path_completes(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch, unfrozen: None
) -> None:
    """report (open_case) -> decide (INSIDE_TERMS) -> offer -> buyer accepts -> refund COMPLETED."""
    mandate_id, capture_id, buyer_id = "mandate-1", "cap-1", "buyer-1"
    _mock_money_path(
        monkeypatch, mandate_id=mandate_id, capture_id=capture_id, buyer_id=buyer_id
    )

    async def fake_refund_capture(**kwargs):
        return clients.AdapterResult(True, 201, {"refund_id": "R-1"}, "completed")

    monkeypatch.setattr(clients, "refund_capture", fake_refund_capture)

    order_id = uuid4()
    opened = await open_case(
        session,
        OpenCaseCommand(
            order_id=order_id,
            kind=CaseKind.LATE,
            origin=CaseOrigin.DETECTOR,
            source_event_id=None,
            untrusted_text=None,
        ),
    )
    await session.commit()

    decision = await assemble_facts_and_decide(session, opened.case_id, CFG)
    assert decision.klass == PolicyClass.INSIDE_TERMS
    assert decision.amount_minor == 2000

    offer = await create_offer(
        session, opened.case_id, decision, Action.REFUND, ApprovalTier.CONFIRM
    )
    await session.commit()

    accept_result = await accept_offer(
        session, offer.offer_id, buyer_id, offer.proposal_hash
    )
    await session.commit()
    assert accept_result.state == "APPROVED"
    assert accept_result.replayed is False

    outcome = await execute_refund(session, opened.case_id)
    await session.commit()

    assert outcome.execution == "DONE"
    assert outcome.case_state == "RESOLVED_REFUNDED"
    assert outcome.attempt_status is not None
    assert outcome.attempt_status.value == "COMPLETED"

    case = await repo.get_case(session, opened.case_id)
    assert case is not None
    assert case["state"] == "RESOLVED_REFUNDED"

    attempt = await repo.get_attempt_for_case(session, opened.case_id)
    assert attempt is not None
    assert attempt["status"] == "COMPLETED"
    assert attempt["paypal_refund_id"] == "R-1"


async def test_accept_offer_rejects_hash_mismatch(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch, unfrozen: None
) -> None:
    _mock_money_path(
        monkeypatch, mandate_id="mandate-2", capture_id="cap-2", buyer_id="buyer-2"
    )

    opened = await open_case(
        session,
        OpenCaseCommand(
            order_id=uuid4(),
            kind=CaseKind.LATE,
            origin=CaseOrigin.DETECTOR,
            source_event_id=None,
            untrusted_text=None,
        ),
    )
    await session.commit()
    decision = await assemble_facts_and_decide(session, opened.case_id, CFG)
    offer = await create_offer(
        session, opened.case_id, decision, Action.REFUND, ApprovalTier.CONFIRM
    )
    await session.commit()

    with pytest.raises(ValueError):
        await accept_offer(session, offer.offer_id, "buyer-2", "not-the-real-hash")


async def test_execute_refund_blocked_when_frozen(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Kill switch wins over an APPROVED case: no attempt row, execution=QUEUED_FROZEN."""
    mandate_id, capture_id, buyer_id = "mandate-3", "cap-3", "buyer-3"
    _mock_money_path(
        monkeypatch, mandate_id=mandate_id, capture_id=capture_id, buyer_id=buyer_id
    )

    opened = await open_case(
        session,
        OpenCaseCommand(
            order_id=uuid4(),
            kind=CaseKind.LATE,
            origin=CaseOrigin.DETECTOR,
            source_event_id=None,
            untrusted_text=None,
        ),
    )
    await session.commit()
    decision = await assemble_facts_and_decide(session, opened.case_id, CFG)
    offer = await create_offer(
        session, opened.case_id, decision, Action.REFUND, ApprovalTier.CONFIRM
    )
    await session.commit()
    await accept_offer(session, offer.offer_id, buyer_id, offer.proposal_hash)
    await session.commit()

    # _clean_tables leaves refunds_frozen = true by default (no `unfrozen` fixture here).
    outcome = await execute_refund(session, opened.case_id)
    await session.commit()

    assert outcome.execution == "QUEUED_FROZEN"
    assert outcome.attempt_status is None

    case = await repo.get_case(session, opened.case_id)
    assert case is not None
    assert case["state"] == "APPROVED"


async def test_buyer_report_reclassifies_kind_from_triage_on_first_pass(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The actual bug fix: a BUYER_REPORT case opens as a kind=OTHER placeholder, and the
    first assemble_facts_and_decide pass reclassifies it to triage's real category and
    persists that back to the cases row (not just the in-memory DecisionFacts)."""
    mandate_id, capture_id, buyer_id = "mandate-4", "cap-4", "buyer-4"
    _mock_money_path(
        monkeypatch, mandate_id=mandate_id, capture_id=capture_id, buyer_id=buyer_id
    )

    async def fake_triage(**kwargs):
        return clients.TriageResult(
            category=CaseKind.DAMAGED,
            confidence=0.88,
            route="PROCEED",
            reasons=["item arrived damaged per buyer photos"],
            injection_suspected=False,
        )

    monkeypatch.setattr(clients, "classify_triage", fake_triage)

    opened = await open_case(
        session,
        OpenCaseCommand(
            order_id=uuid4(),
            kind=CaseKind.OTHER,
            origin=CaseOrigin.BUYER_REPORT,
            source_event_id=None,
            untrusted_text="it arrived broken",
        ),
    )
    await session.commit()

    await assemble_facts_and_decide(session, opened.case_id, CFG)
    await session.commit()

    case = await repo.get_case(session, opened.case_id)
    assert case is not None
    assert case["kind"] == CaseKind.DAMAGED.value

    # A re-evaluation pass (case is no longer in PROBLEM_DETECTED) must not flip kind again,
    # even if triage were to return a different category.
    async def fake_triage_other(**kwargs):
        return clients.TriageResult(
            category=CaseKind.WRONG_ITEM,
            confidence=0.9,
            route="PROCEED",
            reasons=[],
            injection_suspected=False,
        )

    monkeypatch.setattr(clients, "classify_triage", fake_triage_other)
    await assemble_facts_and_decide(session, opened.case_id, CFG)
    await session.commit()

    case_after = await repo.get_case(session, opened.case_id)
    assert case_after is not None
    assert case_after["kind"] == CaseKind.DAMAGED.value


async def test_buyer_report_kind_reclassification_skips_on_collision(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If a case already exists for (order_id, triage's proposed kind) -- e.g. a DETECTOR
    case for the same order under LATE -- the reclassification is skipped rather than
    risking the (order_id, kind) unique constraint; the BUYER_REPORT case stays OTHER."""
    order_id = uuid4()
    mandate_id, capture_id, buyer_id = "mandate-5", "cap-5", "buyer-5"
    _mock_money_path(
        monkeypatch, mandate_id=mandate_id, capture_id=capture_id, buyer_id=buyer_id
    )

    async def fake_triage_other(**kwargs):
        return None

    monkeypatch.setattr(clients, "classify_triage", fake_triage_other)
    await open_case(
        session,
        OpenCaseCommand(
            order_id=order_id,
            kind=CaseKind.LATE,
            origin=CaseOrigin.DETECTOR,
            source_event_id=uuid4(),
            untrusted_text=None,
        ),
    )
    await session.commit()

    async def fake_triage_late(**kwargs):
        return clients.TriageResult(
            category=CaseKind.LATE,
            confidence=0.9,
            route="PROCEED",
            reasons=[],
            injection_suspected=False,
        )

    monkeypatch.setattr(clients, "classify_triage", fake_triage_late)
    opened = await open_case(
        session,
        OpenCaseCommand(
            order_id=order_id,
            kind=CaseKind.OTHER,
            origin=CaseOrigin.BUYER_REPORT,
            source_event_id=None,
            untrusted_text="still hasn't arrived",
        ),
    )
    await session.commit()

    await assemble_facts_and_decide(session, opened.case_id, CFG)
    await session.commit()

    case = await repo.get_case(session, opened.case_id)
    assert case is not None
    assert case["kind"] == CaseKind.OTHER.value
