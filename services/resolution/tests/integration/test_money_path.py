"""Integration tests against a real throwaway Postgres: lazy case materialization, the CAS
transition path, the policy decision fail-closed path, and the full INSIDE_TERMS
report -> decide -> offer -> accept -> refund saga (money path). mandate/checkout/tracking/
paypal-adapter are mocked via monkeypatch on app.clients (no real HTTP calls, real DB underneath).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app import clients, repo
from app.domain.policy import CaptureFacts, PolicyClass, PolicyConfig, TermsSnapshot
from app.domain.proposal import Action, ApprovalTier
from app.domain.states import Actor, CaseKind, CaseOrigin, CaseState, IllegalTransition
from app.settings import settings as app_settings
from app.usecases.decide import assemble_facts_and_decide
from app.usecases.execute_refund import execute_refund, reconcile_attempts
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


# ---------------------------------------------------------------------------
# Reconcile: SENT/UNKNOWN attempts (api.md s3.10, spec s8) -- simulates "our connection to
# paypal-adapter timed out/errored (UNKNOWN), but find out later what actually happened" by
# mocking clients.refund_capture to return a 5xx/timeout-shaped AdapterResult (triggers
# execute_refund's UNKNOWN branch), then mocking clients.get_refund for reconcile_attempts's
# own follow-up read. No prior test in this suite exercised reconcile_attempts at all.
# ---------------------------------------------------------------------------


async def _drive_to_unknown_attempt(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    *,
    mandate_id: str,
    capture_id: str,
    buyer_id: str,
):
    _mock_money_path(
        monkeypatch, mandate_id=mandate_id, capture_id=capture_id, buyer_id=buyer_id
    )

    async def fake_refund_capture_timeout(**kwargs):
        # status_code=504/None and no body -- matches execute_refund's final "else" branch
        # (timeout/5xx/connection error/unimplemented -> UNKNOWN, reconcile decides).
        return clients.AdapterResult(False, 504, None, "timeout")

    monkeypatch.setattr(clients, "refund_capture", fake_refund_capture_timeout)

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

    outcome = await execute_refund(session, opened.case_id)
    await session.commit()
    assert outcome.execution == "IN_PROGRESS"
    assert outcome.attempt_status is not None
    assert outcome.attempt_status.value == "UNKNOWN"

    # get_reconcilable_attempts requires sent_at older than refund_min_reconcile_age_s
    # (default 60s, far too slow for a test) -- 0 it out for this test only.
    monkeypatch.setattr(app_settings, "refund_min_reconcile_age_s", 0)

    attempt = await repo.get_attempt_for_case(session, opened.case_id)
    assert attempt is not None
    return opened.case_id, attempt["id"]


async def test_reconcile_resolves_unknown_attempt_to_completed(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch, unfrozen: None
) -> None:
    case_id, attempt_id = await _drive_to_unknown_attempt(
        session,
        monkeypatch,
        mandate_id="mandate-r1",
        capture_id="cap-r1",
        buyer_id="buyer-r1",
    )
    # Simulate: the original refund_capture call DID reach PayPal and get an id back, but
    # OUR read of the confirmation timed out (the realistic "timeout-after-success" case) --
    # a known paypal_refund_id routes reconcile through get_refund (a pure read, no frozen
    # gate), not reconcile_refund (a potential-replay, frozen-gated -- see the other tests).
    await repo.update_attempt_status(
        session,
        attempt_id=attempt_id,
        new_status="UNKNOWN",
        paypal_refund_id="R-TIMEOUT-1",
    )
    await session.commit()

    async def fake_get_refund(refund_id, token=None):
        assert refund_id == "R-TIMEOUT-1"
        return clients.AdapterResult(
            True, 200, {"status": "COMPLETED", "id": refund_id}, "ok"
        )

    monkeypatch.setattr(clients, "get_refund", fake_get_refund)

    summary = await reconcile_attempts(session, 25)
    await session.commit()

    assert summary.examined == 1
    assert summary.finalized_completed == 1
    assert summary.still_unknown == 0

    case = await repo.get_case(session, case_id)
    assert case is not None
    assert case["state"] == "RESOLVED_REFUNDED"
    attempt = await repo.get_attempt_for_case(session, case_id)
    assert attempt is not None
    assert attempt["status"] == "COMPLETED"


async def test_reconcile_resolves_unknown_attempt_to_failed(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch, unfrozen: None
) -> None:
    case_id, attempt_id = await _drive_to_unknown_attempt(
        session,
        monkeypatch,
        mandate_id="mandate-r2",
        capture_id="cap-r2",
        buyer_id="buyer-r2",
    )
    await repo.update_attempt_status(
        session,
        attempt_id=attempt_id,
        new_status="UNKNOWN",
        paypal_refund_id="R-TIMEOUT-2",
    )
    await session.commit()

    async def fake_get_refund(refund_id, token=None):
        return clients.AdapterResult(
            True, 200, {"status": "FAILED", "id": refund_id}, "ok"
        )

    monkeypatch.setattr(clients, "get_refund", fake_get_refund)

    summary = await reconcile_attempts(session, 25)
    await session.commit()

    assert summary.examined == 1
    assert summary.finalized_failed == 1

    case = await repo.get_case(session, case_id)
    assert case is not None
    assert case["state"] == "HUMAN_REVIEW"
    attempt = await repo.get_attempt_for_case(session, case_id)
    assert attempt is not None
    assert attempt["status"] == "FAILED"


async def test_reconcile_leaves_still_ambiguous_attempt_as_unknown(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch, unfrozen: None
) -> None:
    """No paypal_refund_id was ever captured (our original call never got that far before
    timing out) -- reconcile routes through reconcile_refund(request_id) instead of
    get_refund. That call is itself still ambiguous (another timeout/5xx): reconcile must
    not guess: the attempt and case both stay exactly where they were, to be retried later."""
    case_id, _attempt_id = await _drive_to_unknown_attempt(
        session,
        monkeypatch,
        mandate_id="mandate-r3",
        capture_id="cap-r3",
        buyer_id="buyer-r3",
    )

    async def fake_reconcile_refund_still_down(request_id, token=None):
        return clients.AdapterResult(False, 504, None, "timeout")

    monkeypatch.setattr(clients, "reconcile_refund", fake_reconcile_refund_still_down)

    summary = await reconcile_attempts(session, 25)
    await session.commit()

    assert summary.examined == 1
    assert summary.still_unknown == 1
    assert summary.finalized_completed == 0
    assert summary.finalized_failed == 0

    case = await repo.get_case(session, case_id)
    assert case is not None
    assert case["state"] == "REFUNDING"
    attempt = await repo.get_attempt_for_case(session, case_id)
    assert attempt is not None
    assert attempt["status"] == "UNKNOWN"


async def test_reconcile_with_known_refund_id_still_reads_while_frozen(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch, unfrozen: None
) -> None:
    """spec s8/s9: a known paypal_refund_id routes reconcile through get_refund (a pure
    read), which runs regardless of the freeze flag and still finalizes a COMPLETED result
    -- freezing blocks NEW replay attempts (the no-refund-id reconcile_refund path, see
    test_reconcile_skips_replay_while_frozen_with_no_known_refund_id below), not reads of
    what's already known to have happened on PayPal's side."""
    case_id, attempt_id = await _drive_to_unknown_attempt(
        session,
        monkeypatch,
        mandate_id="mandate-r4",
        capture_id="cap-r4",
        buyer_id="buyer-r4",
    )
    await repo.update_attempt_status(
        session,
        attempt_id=attempt_id,
        new_status="UNKNOWN",
        paypal_refund_id="R-TIMEOUT-4",
    )
    await session.commit()

    from sqlalchemy import text as sa_text

    await session.execute(
        sa_text(
            "UPDATE resolution.control_flags SET refunds_frozen = true, epoch = epoch + 1 WHERE id = 1"
        )
    )
    await session.commit()

    async def fake_get_refund(refund_id, token=None):
        return clients.AdapterResult(
            True, 200, {"status": "COMPLETED", "id": refund_id}, "ok"
        )

    monkeypatch.setattr(clients, "get_refund", fake_get_refund)

    summary = await reconcile_attempts(session, 25)
    await session.commit()

    assert summary.examined == 1
    assert summary.finalized_completed == 1
    assert summary.frozen_skipped_replays == 0

    case = await repo.get_case(session, case_id)
    assert case is not None
    assert case["state"] == "RESOLVED_REFUNDED"


async def test_reconcile_skips_replay_while_frozen_with_no_known_refund_id(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch, unfrozen: None
) -> None:
    """No paypal_refund_id known yet -- reconcile would need reconcile_refund (a
    potential-replay call), which is correctly frozen-gated (spec s9): no PayPal call at
    all while frozen, attempt and case stay exactly where they were."""
    case_id, _attempt_id = await _drive_to_unknown_attempt(
        session,
        monkeypatch,
        mandate_id="mandate-r5",
        capture_id="cap-r5",
        buyer_id="buyer-r5",
    )

    from sqlalchemy import text as sa_text

    await session.execute(
        sa_text(
            "UPDATE resolution.control_flags SET refunds_frozen = true, epoch = epoch + 1 WHERE id = 1"
        )
    )
    await session.commit()

    called = False

    async def fake_reconcile_refund_should_not_be_called(request_id, token=None):
        nonlocal called
        called = True
        return clients.AdapterResult(True, 200, {"status": "COMPLETED"}, "ok")

    monkeypatch.setattr(
        clients, "reconcile_refund", fake_reconcile_refund_should_not_be_called
    )

    summary = await reconcile_attempts(session, 25)
    await session.commit()

    assert called is False  # frozen must block the call entirely, not just its effect
    assert summary.examined == 1
    assert summary.frozen_skipped_replays == 1
    assert summary.finalized_completed == 0

    case = await repo.get_case(session, case_id)
    assert case is not None
    assert case["state"] == "REFUNDING"


# ---------------------------------------------------------------------------
# Concurrency: duplicate/simultaneous accept_offer calls for the SAME offer must resolve
# to exactly one winner, never a double-refund -- each concurrent caller needs its own
# AsyncSession (one session cannot run two concurrent statements), so this test builds its
# own engine/sessionmaker against the same throwaway test DB the `session` fixture uses.
# ---------------------------------------------------------------------------


def _sqlalchemy_dsn_for_test(pg_env: dict) -> str:
    return (
        f"postgresql+asyncpg://svc_resolution:{pg_env['svc_password']}"
        f"@localhost:5432/{pg_env['db_name']}"
    )


async def test_concurrent_accept_offer_has_exactly_one_winner(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch, unfrozen: None, pg_env: dict
) -> None:
    mandate_id, capture_id, buyer_id = "mandate-c1", "cap-c1", "buyer-c1"
    _mock_money_path(
        monkeypatch, mandate_id=mandate_id, capture_id=capture_id, buyer_id=buyer_id
    )

    call_count = 0

    async def fake_refund_capture(**kwargs):
        nonlocal call_count
        call_count += 1
        return clients.AdapterResult(
            True, 201, {"refund_id": f"R-CONCURRENT-{call_count}"}, "completed"
        )

    monkeypatch.setattr(clients, "refund_capture", fake_refund_capture)

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

    engine = create_async_engine(
        _sqlalchemy_dsn_for_test(pg_env), future=True, pool_size=10, max_overflow=10
    )
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def one_accept():
        async with maker() as s:
            try:
                result = await accept_offer(
                    s, offer.offer_id, buyer_id, offer.proposal_hash
                )
                await s.commit()
                return ("ok", result)
            except Exception as exc:  # noqa: BLE001
                await s.rollback()
                return ("error", exc)

    results = await asyncio.gather(*[one_accept() for _ in range(8)])
    await engine.dispose()

    ok_results = [r for kind, r in results if kind == "ok"]
    assert (
        len(ok_results) == 8
    )  # CAS makes every caller see a clean result, winner or replay
    winners = [r for r in ok_results if not r.replayed]
    assert len(winners) == 1  # exactly one caller actually won the accept race

    final_offer = await repo.get_offer(session, offer.offer_id)
    assert final_offer is not None
    assert final_offer["status"] == "ACCEPTED"

    case = await repo.get_case(session, opened.case_id)
    assert case is not None
    assert case["state"] == "APPROVED"

    # execute_refund is what the route handler calls next after a winning accept (mirrors
    # accept_offer_route/consent_approval) -- racing it too must still produce exactly one
    # real PayPal call, with every caller converging on the same final state.
    engine2 = create_async_engine(
        _sqlalchemy_dsn_for_test(pg_env), future=True, pool_size=10, max_overflow=10
    )
    maker2 = async_sessionmaker(engine2, expire_on_commit=False, class_=AsyncSession)

    async def one_execute():
        async with maker2() as s:
            outcome = await execute_refund(s, opened.case_id)
            await s.commit()
            return outcome

    outcomes = await asyncio.gather(*[one_execute() for _ in range(5)])
    await engine2.dispose()

    assert (
        call_count == 1
    )  # exactly one real PayPal call, no matter how many callers raced
    completed = [o for o in outcomes if o.execution == "DONE"]
    assert len(completed) >= 1

    final_case = await repo.get_case(session, opened.case_id)
    assert final_case is not None
    assert final_case["state"] == "RESOLVED_REFUNDED"
    attempt = await repo.get_attempt_for_case(session, opened.case_id)
    assert attempt is not None
    assert attempt["status"] == "COMPLETED"
