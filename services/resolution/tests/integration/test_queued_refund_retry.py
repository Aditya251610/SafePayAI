"""A refund queued while REFUNDS_FROZEN (execute_refund's "frozen -> stay APPROVED,
QUEUED_FROZEN, no attempt row" path, spec s9) previously had no retry mechanism at all:
reconcile_attempts only reads refund_attempts rows, and a queued case has none.
/internal/tick now also re-drives APPROVED cases with no attempt row through
execute_refund once unfrozen."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app import clients, repo
from app.domain.proposal import Action, ApprovalTier
from app.domain.states import CaseKind, CaseOrigin
from app.routers.internal import internal_tick
from app.usecases.decide import assemble_facts_and_decide
from app.usecases.execute_refund import execute_refund
from app.usecases.offers import accept_offer, create_offer
from app.usecases.open_case import OpenCaseCommand, open_case
from tests.integration.test_money_path import CFG, _mock_money_path

pytestmark = pytest.mark.asyncio


async def test_queued_refund_is_retried_once_unfrozen(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No `unfrozen` fixture -- _clean_tables resets REFUNDS_FROZEN = true by default,
    # which is exactly the state this test needs to start in.
    _mock_money_path(
        monkeypatch,
        mandate_id="mandate-queued",
        capture_id="cap-queued",
        buyer_id="buyer-queued",
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
    await accept_offer(session, offer.offer_id, "buyer-queued", offer.proposal_hash)
    await session.commit()

    outcome = await execute_refund(session, opened.case_id)
    await session.commit()
    assert outcome.execution == "QUEUED_FROZEN"
    assert outcome.attempt_status is None
    assert await repo.get_attempt_for_case(session, opened.case_id) is None

    case = await repo.get_case(session, opened.case_id)
    assert case is not None
    assert case["state"] == "APPROVED"

    # Unfreeze, then drive the tick.
    from sqlalchemy import text as sa_text

    await session.execute(
        sa_text(
            "UPDATE resolution.control_flags SET refunds_frozen = false, epoch = epoch + 1 WHERE id = 1"
        )
    )
    await session.commit()

    async def fake_refund_capture(**kwargs):
        return clients.AdapterResult(
            True, 201, {"status": "COMPLETED", "id": "R-QUEUED-1"}, "ok"
        )

    monkeypatch.setattr(clients, "refund_capture", fake_refund_capture)

    tick_result = await internal_tick(_=None, session=session)
    assert tick_result["queued_retried"] == 1

    attempt = await repo.get_attempt_for_case(session, opened.case_id)
    assert attempt is not None
    assert attempt["status"] == "COMPLETED"
    case_after = await repo.get_case(session, opened.case_id)
    assert case_after is not None
    assert case_after["state"] == "RESOLVED_REFUNDED"
