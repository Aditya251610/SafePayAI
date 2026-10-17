"""assemble_facts_and_decide maps tracking's own ShipmentStatus vocabulary onto
triage-ai's exact ShipStatus contract before calling classify_triage -- this used
to always send an empty timeline regardless of real shipment history (see
decide.py's _TRACKING_TO_TRIAGE_STATUS), and always sent item_titles=[] since
checkout's GET /orders/{id} never carried any (now it does, via
clients.OrderStateFacts.item_titles)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app_resolution import clients
from app_resolution.domain.policy import PolicyClass, PolicyConfig
from app_resolution.domain.states import CaseKind, CaseOrigin
from app_resolution.usecases.decide import assemble_facts_and_decide
from app_resolution.usecases.open_case import OpenCaseCommand, open_case

CFG = PolicyConfig(
    policy_version="v1",
    refund_cap_minor=5000,
    excluded_categories=frozenset(),
    velocity_max=2,
    velocity_window_days=30,
    triage_min_confidence=0.7,
)


async def test_timeline_payload_is_mapped_from_tracking_events(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict = {}

    async def fake_identity(order_id: str, token: str | None = None):
        return (
            None,
            None,
            None,
        )  # mandate unreachable -> fails closed, fine for this test

    async def fake_tracking(order_id: str, kind: CaseKind, token: str | None = None):
        return clients.TrackingFacts(
            carrier_status="IN_TRANSIT",
            carrier_agrees=True,
            events=[
                {
                    "event_id": "ignored-tracking-side-id",
                    "status": "LABEL_CREATED",
                    "occurred_at_sim": "2026-01-01T00:00:00+00:00",
                    "note_code": None,
                },
                {
                    "event_id": "ignored-tracking-side-id-2",
                    "status": "EXCEPTION",
                    "occurred_at_sim": "2026-01-03T00:00:00+00:00",
                    "note_code": "CARRIER_DELAY",
                },
                {
                    "event_id": "ignored-tracking-side-id-3",
                    "status": "SOME_FUTURE_STATUS_NOT_YET_MAPPED",
                    "occurred_at_sim": "2026-01-04T00:00:00+00:00",
                    "note_code": None,
                },
            ],
        )

    async def fake_order_state(order_id: str, token: str | None = None):
        return clients.OrderStateFacts(
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            status="CAPTURED",
            item_titles=["Trail Running Socks, 3-pack"],
        )

    async def fake_classify(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(clients, "get_order_identity", fake_identity)
    monkeypatch.setattr(clients, "get_tracking_agreement", fake_tracking)
    monkeypatch.setattr(clients, "get_order_state_facts", fake_order_state)
    monkeypatch.setattr(clients, "classify_triage", fake_classify)

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
    assert (
        decision.klass == PolicyClass.HUMAN_REVIEW
    )  # mandate unreachable, fails closed

    timeline = captured["timeline"]
    assert [e["status"] for e in timeline] == ["LABEL_CREATED", "DELAYED", "UNKNOWN"]
    assert timeline[1]["note"] == "CARRIER_DELAY"
    # event_id is regenerated here, not tracking's own id -- only this usecase's
    # mapping shape matters to triage-ai's schema (pattern-constrained field).
    assert timeline[0]["event_id"] != "ignored-tracking-side-id"

    order_facts = captured["order"]
    assert order_facts["item_titles"] == ["Trail Running Socks, 3-pack"]
