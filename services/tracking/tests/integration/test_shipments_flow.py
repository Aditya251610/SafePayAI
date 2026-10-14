"""Integration tests against a real throwaway Postgres: create_shipment -> tick -> detection,
cancel_shipment, and the demo-clock advance path. checkout/paypal-adapter are mocked via
monkeypatch on app.clients (no real HTTP calls in tests, real DB underneath).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import clients, repo
from app.domain.shipment_states import OutcomeProfile, PaypalSync, ShipmentStatus
from app.usecases.demo import DemoActor, advance_clock
from app.usecases.shipments import (
    CreateShipmentCommand,
    cancel_shipment,
    create_shipment,
)
from app.usecases.tick import TickTrigger, run_tick


class _FakeOrderFacts:
    def __init__(self, status: str = "CAPTURED") -> None:
        self.order_id = "order-1"
        self.status = status
        self.capture_id = "cap-1"
        self.mandate_id = "mandate-1"
        self.protected_until = datetime.now(UTC) + timedelta(days=7)


@pytest.fixture(autouse=True)
def _stub_checkout_and_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_order_facts(order_id: str, token: str | None = None):
        return _FakeOrderFacts()

    async def fake_add_tracking(**kwargs):
        return clients.AdapterResult(True, 201, {}, "ok")

    async def fake_cancel_tracking(**kwargs):
        return clients.AdapterResult(True, 204, None, "ok")

    monkeypatch.setattr(clients, "get_order_facts", fake_get_order_facts)
    monkeypatch.setattr(clients, "add_tracking", fake_add_tracking)
    monkeypatch.setattr(clients, "cancel_tracking", fake_cancel_tracking)


async def test_create_shipment_persists_and_syncs_paypal(session: AsyncSession) -> None:
    cmd = CreateShipmentCommand(
        order_id="order-1",
        tracking_number="TRACK123",
        carrier_name="DemoCarrier",
        outcome_profile=OutcomeProfile.ON_TIME,
        actor_sub="merchant-1",
        idempotency_key=None,
    )
    result = await create_shipment(session, cmd)

    assert result.status == ShipmentStatus.LABEL_CREATED
    assert result.paypal_sync == PaypalSync.ADDED
    assert not result.replayed

    row = await repo.get_shipment(session, result.shipment_id)
    assert row is not None
    assert row["capture_id"] == "cap-1"
    assert row["mandate_id"] == "mandate-1"


async def test_create_shipment_is_idempotent_on_duplicate(
    session: AsyncSession,
) -> None:
    cmd = CreateShipmentCommand(
        order_id="order-1",
        tracking_number="TRACK123",
        carrier_name="DemoCarrier",
        outcome_profile=OutcomeProfile.ON_TIME,
        actor_sub="merchant-1",
        idempotency_key=None,
    )
    first = await create_shipment(session, cmd)
    second = await create_shipment(session, cmd)

    assert second.shipment_id == first.shipment_id
    assert second.replayed is True


async def test_create_shipment_rejects_order_not_captured(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_not_captured(order_id: str, token: str | None = None):
        return _FakeOrderFacts(status="APPROVED")

    monkeypatch.setattr(clients, "get_order_facts", fake_not_captured)

    cmd = CreateShipmentCommand(
        order_id="order-2",
        tracking_number="TRACK999",
        carrier_name="DemoCarrier",
        outcome_profile=OutcomeProfile.ON_TIME,
        actor_sub="merchant-1",
        idempotency_key=None,
    )
    with pytest.raises(ValueError):
        await create_shipment(session, cmd)


async def test_lost_outcome_profile_detects_after_clock_advance(
    session: AsyncSession,
) -> None:
    cmd = CreateShipmentCommand(
        order_id="order-lost",
        tracking_number="TRACKLOST",
        carrier_name="DemoCarrier",
        outcome_profile=OutcomeProfile.LOST,
        actor_sub="merchant-1",
        idempotency_key=None,
    )
    created = await create_shipment(session, cmd)
    await session.commit()

    actor = DemoActor(actor_sub="merchant-1", role="merchant", trace_id=None)
    # Advance well past the LOST threshold (default lost_after_seconds = 604800 = 7 days).
    _result, tick = await advance_clock(
        session, 8 * 86400, "TEST_ADVANCE", "idem-1", actor, 30 * 86400
    )

    assert tick.detected_count >= 1

    detections = await session.execute(
        text("SELECT kind FROM tracking.detections WHERE shipment_id = :id"),
        {"id": created.shipment_id},
    )
    kinds = {row[0] for row in detections.all()}
    assert "LOST" in kinds

    outbox = await session.execute(
        text("SELECT type FROM tracking.outbox WHERE aggregate_id = :id"),
        {"id": str(created.shipment_id)},
    )
    types = {row[0] for row in outbox.all()}
    assert "shipment.lost_detected" in types


async def test_run_tick_skips_when_lease_held(session: AsyncSession) -> None:
    held = await repo.try_acquire_lease(
        session, name="detector", holder="someone-else", ttl_seconds=300
    )
    assert held is True
    await session.commit()

    result = await run_tick(session, TickTrigger.MANUAL)
    assert result.skipped_lease is True


async def test_cancel_shipment_moves_to_cancelled(session: AsyncSession) -> None:
    cmd = CreateShipmentCommand(
        order_id="order-cancel",
        tracking_number="TRACKCANCEL",
        carrier_name="DemoCarrier",
        outcome_profile=OutcomeProfile.ON_TIME,
        actor_sub="merchant-1",
        idempotency_key=None,
    )
    created = await create_shipment(session, cmd)
    await session.commit()

    paypal_sync = await cancel_shipment(
        session, created.shipment_id, "MERCHANT_CANCEL", "merchant-1"
    )
    assert paypal_sync in (PaypalSync.CANCELLED, PaypalSync.FAILED)

    row = await repo.get_shipment(session, created.shipment_id)
    assert row is not None
    assert row["status"] == ShipmentStatus.CANCELLED.value
    assert row["active"] is False


async def test_get_shipment_events_by_order_returns_full_history(
    session: AsyncSession,
) -> None:
    """Real per-event history backing GET /shipments/{order_id}'s new `events`
    field (built for triage-ai's timeline input, see resolution's decide.py)."""
    cmd = CreateShipmentCommand(
        order_id="order-events",
        tracking_number="TRACKEVENTS",
        carrier_name="DemoCarrier",
        outcome_profile=OutcomeProfile.ON_TIME,
        actor_sub="merchant-1",
        idempotency_key=None,
    )
    created = await create_shipment(session, cmd)
    await session.commit()

    await cancel_shipment(session, created.shipment_id, "MERCHANT_CANCEL", "merchant-1")
    await session.commit()

    events = await repo.get_shipment_events_by_order(session, "order-events")
    assert [e["to_status"] for e in events] == [
        ShipmentStatus.LABEL_CREATED.value,
        ShipmentStatus.CANCELLED.value,
    ]
    assert events[0]["occurred_at_sim"] <= events[1]["occurred_at_sim"]
    assert all(e["shipment_id"] == created.shipment_id for e in events)
