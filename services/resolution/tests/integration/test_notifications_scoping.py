"""GET /notifications' repo layer (app.repo.get_notifications): APPROVAL_LINK
notifications must never be visible in the unscoped (merchant) view -- their body is a
single-use bearer consent token/URL (api.md section 3.7). Previously buyer_id=None
(merchant) returned every notification unfiltered, including other buyers' approval
links -- a real cross-buyer leak of a bearer credential, not just an IDOR."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app import repo

pytestmark = pytest.mark.asyncio


async def test_unscoped_view_excludes_approval_links_but_sees_other_types(
    session: AsyncSession,
) -> None:
    case_id = uuid4()
    buyer_a = f"buyer-{uuid4().hex[:8]}"
    buyer_b = f"buyer-{uuid4().hex[:8]}"

    await repo.insert_notification(
        session,
        case_id=case_id,
        buyer_id=buyer_a,
        type="APPROVAL_LINK",
        body="https://approvals.test/approvals/secret-token-a",
    )
    await repo.insert_notification(
        session,
        case_id=case_id,
        buyer_id=buyer_b,
        type="APPROVAL_LINK",
        body="https://approvals.test/approvals/secret-token-b",
    )
    await repo.insert_notification(
        session,
        case_id=case_id,
        buyer_id=buyer_a,
        type="CASE_UPDATED",
        body="your case was updated",
    )
    await session.commit()

    unscoped = await repo.get_notifications(session, buyer_id=None)
    types = {row["type"] for row in unscoped}
    assert "APPROVAL_LINK" not in types
    assert "CASE_UPDATED" in types

    scoped_to_a = await repo.get_notifications(session, buyer_id=buyer_a)
    scoped_types_and_bodies = {(r["type"], r["body"]) for r in scoped_to_a}
    assert ("APPROVAL_LINK", "https://approvals.test/approvals/secret-token-a") in (
        scoped_types_and_bodies
    )
    assert not any(
        body == "https://approvals.test/approvals/secret-token-b"
        for _type, body in scoped_types_and_bodies
    )
