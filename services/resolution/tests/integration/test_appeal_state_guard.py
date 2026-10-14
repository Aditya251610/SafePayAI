"""POST /cases/{id}/appeal (T24: DECLINED -> HUMAN_REVIEW, "buyer appeals") must only
fire from DECLINED. apply_transition's is_legal_transition only checks the (from, to)
STATE pair, not which transition_id is allowed to produce it -- REFUNDING -> HUMAN_REVIEW
is ALSO a legal pair (a different, system-initiated escalation), so without an explicit
state guard a buyer could call appeal while their own case is mid-refund and push it into
HUMAN_REVIEW while the refund still completes at PayPal underneath."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import repo
from app.domain.states import CaseKind, CaseOrigin, CaseState
from app.routers.cases import appeal_case
from app.schemas.cases import AppealRequest

pytestmark = pytest.mark.asyncio


async def _make_case(session: AsyncSession, *, state: CaseState, buyer_id: str) -> str:
    case_id = uuid4()
    await repo.insert_case(
        session,
        case_id=case_id,
        order_id=f"order-{case_id.hex[:8]}",
        capture_id=None,
        mandate_id=None,
        buyer_id=buyer_id,
        kind=CaseKind.LATE.value,
        origin=CaseOrigin.DETECTOR.value,
        state=state.value,
        terms_snapshot=None,
        terms_hash=None,
        opened_at=datetime.now(UTC),
        window_hold=False,
        untrusted_text=None,
    )
    await session.commit()
    return str(case_id)


async def test_appeal_from_declined_succeeds(session: AsyncSession) -> None:
    buyer_id = f"buyer-{uuid4().hex[:8]}"
    case_id = await _make_case(session, state=CaseState.DECLINED, buyer_id=buyer_id)

    result = await appeal_case(
        case_id,
        AppealRequest(note=None),
        claims={"sub": buyer_id},
        session=session,
    )
    assert result.state == "HUMAN_REVIEW"


async def test_appeal_mid_refund_is_rejected(session: AsyncSession) -> None:
    buyer_id = f"buyer-{uuid4().hex[:8]}"
    case_id = await _make_case(session, state=CaseState.REFUNDING, buyer_id=buyer_id)

    with pytest.raises(HTTPException) as exc_info:
        await appeal_case(
            case_id,
            AppealRequest(note=None),
            claims={"sub": buyer_id},
            session=session,
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "ILLEGAL_TRANSITION"

    # Confirm the case genuinely never moved.
    fresh = await repo.get_case(session, UUID(case_id))
    assert fresh is not None
    assert fresh["state"] == CaseState.REFUNDING.value
