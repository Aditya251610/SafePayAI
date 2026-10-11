"""Shipment use cases: create (add tracking), scripted/forced transition apply, and cancel.

Implements tracking/spec.md section 2 (transitions apply through the table, with shipment_events
rows), section 7 (server-derived capture/mandate ids, idempotent duplicate), section 1 (PayPal
tracker is a best-effort signal, never a decision input) and api.md POST /shipments and cancel.
Scaffold only; bodies are yours to write.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app import clients, repo
from app.domain.shipment_states import (
    DELIVERED_AFTER_LOST_EDGE,
    Anomaly,
    IllegalTransition,
    OutcomeProfile,
    PaypalSync,
    ShipmentStatus,
    TransitionSource,
    is_legal_transition,
)
from app.settings import settings


def _build_script(
    outcome_profile: OutcomeProfile, created_at_sim: datetime, promised_at_sim: datetime
) -> list[tuple[int, datetime, ShipmentStatus]]:
    """Deterministic scripted carrier steps per outcome profile (spec s2 'materialised at
    creation (deterministic, no randomness)'). Judgment call: exact offsets are ours (I); the
    important property is determinism, not the specific timing.
    """
    in_transit_at = created_at_sim + timedelta(hours=1)
    if outcome_profile == OutcomeProfile.ON_TIME:
        return [
            (1, in_transit_at, ShipmentStatus.IN_TRANSIT),
            (2, promised_at_sim - timedelta(hours=1), ShipmentStatus.OUT_FOR_DELIVERY),
            (3, promised_at_sim - timedelta(minutes=10), ShipmentStatus.DELIVERED),
        ]
    if outcome_profile == OutcomeProfile.LATE:
        # No further scans after IN_TRANSIT; is_late() fires once sim_now passes promise+grace.
        return [(1, in_transit_at, ShipmentStatus.IN_TRANSIT)]
    if outcome_profile == OutcomeProfile.LOST:
        # No further scans at all; is_lost() fires via the last-event/promise thresholds.
        return [(1, in_transit_at, ShipmentStatus.IN_TRANSIT)]
    if outcome_profile == OutcomeProfile.DELIVERED_AFTER_LATE:
        return [
            (1, in_transit_at, ShipmentStatus.IN_TRANSIT),
            (2, promised_at_sim + timedelta(days=2), ShipmentStatus.DELIVERED),
        ]
    raise ValueError(f"unknown outcome_profile: {outcome_profile}")


@dataclass(frozen=True, slots=True)
class CreateShipmentCommand:
    """Validated input for POST /shipments. capture_id, mandate_id and promise are NOT here
    (server-derived)."""

    order_id: str
    tracking_number: str
    carrier_name: str
    outcome_profile: (
        OutcomeProfile  # only honoured when PS_TRACKING_SANDBOX_MODE; else ON_TIME
    )
    actor_sub: str
    idempotency_key: str | None


@dataclass(frozen=True, slots=True)
class CreatedShipment:
    """Result of create_shipment (api.md 201 body, service-side)."""

    shipment_id: UUID
    order_id: str
    status: ShipmentStatus
    promised_at_sim: datetime
    paypal_sync: PaypalSync
    paypal_tracker_id: str
    replayed: (
        bool  # True when an identical request returned the existing shipment (200)
    )


@dataclass(frozen=True, slots=True)
class AppliedTransition:
    """One applied status change, as written to shipment_events."""

    shipment_id: UUID
    seq: int
    from_status: ShipmentStatus | None
    to_status: ShipmentStatus
    source: TransitionSource
    occurred_at_sim: datetime
    anomaly: Anomaly | None


async def create_shipment(
    session: AsyncSession, cmd: CreateShipmentCommand
) -> CreatedShipment:
    """Create a shipment for a captured order, materialise its script, and add the PayPal tracker.

    Inputs: validated command. Looks up the order from checkout (or orders_seen) for capture_id,
    mandate_id and the demo protection window -> promised_at_sim.
    Output: CreatedShipment. Writes shipments, scheduled_events, shipment_events, outbox
    (shipment.created) in ONE transaction; PayPal add_tracking happens after commit.
    Edge cases: order not CAPTURED -> ORDER_NOT_CAPTURED (409); checkout unreachable -> nothing
    created
    (503); duplicate (order_id, tracking_number) with same body -> replayed=True; different body ->
    409
    DUPLICATE_TRACKING; PayPal failure is NOT an error (paypal_sync=FAILED, retried on ticks).
    """
    existing = await repo.get_shipment_by_order_and_tracking(
        session, cmd.order_id, cmd.tracking_number
    )
    if existing is not None:
        return CreatedShipment(
            shipment_id=existing["id"],
            order_id=existing["order_id"],
            status=ShipmentStatus(existing["status"]),
            promised_at_sim=existing["promised_at_sim"],
            paypal_sync=PaypalSync(existing["paypal_sync"]),
            paypal_tracker_id=existing["paypal_tracker_id"] or "",
            replayed=True,
        )

    order_facts = await clients.get_order_facts(cmd.order_id)
    if order_facts is None:
        raise ConnectionError("checkout unreachable; cannot create shipment (503)")
    if order_facts.status != "CAPTURED":
        raise ValueError("ORDER_NOT_CAPTURED")

    now = repo.now_utc()
    effective_profile = (
        cmd.outcome_profile if settings.sandbox_mode else OutcomeProfile.ON_TIME
    )
    promised_at_sim = order_facts.protected_until or (
        now + timedelta(days=clients.DEFAULT_PROTECTION_WINDOW_DAYS)
    )

    shipment_id = uuid4()
    await repo.insert_shipment(
        session,
        id=shipment_id,
        order_id=cmd.order_id,
        capture_id=order_facts.capture_id,
        mandate_id=order_facts.mandate_id,
        tracking_number=cmd.tracking_number,
        carrier_name=cmd.carrier_name,
        status=ShipmentStatus.LABEL_CREATED.value,
        outcome_profile=effective_profile.value,
        promised_at_sim=promised_at_sim,
        created_at_sim=now,
        paypal_sync=PaypalSync.NOT_ATTEMPTED.value,
        active=True,
        demo=settings.sandbox_mode,
        version=0,
    )

    await repo.insert_shipment_event(
        session,
        shipment_id=shipment_id,
        seq=1,
        from_status=None,
        to_status=ShipmentStatus.LABEL_CREATED.value,
        source=TransitionSource.MERCHANT.value,
        occurred_at_sim=now,
        actor=cmd.actor_sub,
        note_code=None,
    )

    for seq, due_at_sim, to_status in _build_script(
        effective_profile, now, promised_at_sim
    ):
        await repo.insert_scheduled_event(
            session,
            shipment_id=shipment_id,
            seq=seq + 1,
            due_at_sim=due_at_sim,
            to_status=to_status.value,
        )

    await repo.insert_outbox_event(
        session,
        event_id=uuid4(),
        event_type="shipment.created",
        aggregate_id=str(shipment_id),
        payload={
            "shipment_id": str(shipment_id),
            "order_id": cmd.order_id,
            "capture_id": order_facts.capture_id,
            "mandate_id": order_facts.mandate_id,
            "promised_at_sim": promised_at_sim.isoformat(),
            "simulated": True,
        },
    )

    # PayPal add_tracking happens after the DB transaction commits (best-effort, spec s1/s7).
    await session.commit()
    tracker_id = f"{order_facts.capture_id}-{cmd.tracking_number}"
    paypal_sync = PaypalSync.NOT_ATTEMPTED
    try:
        result = await clients.add_tracking(
            order_id=cmd.order_id,
            capture_id=order_facts.capture_id,
            tracking_number=cmd.tracking_number,
            carrier_name=cmd.carrier_name,
        )
        paypal_sync = PaypalSync.ADDED if result.ok else PaypalSync.FAILED
        await repo.update_shipment_paypal_sync(
            session,
            shipment_id=shipment_id,
            paypal_tracker_id=tracker_id if result.ok else None,
            paypal_sync=paypal_sync.value,
            paypal_last_error=None if result.ok else result.detail,
        )
        await session.commit()
    except Exception:  # noqa: BLE001 - PayPal failure never blocks shipment creation (spec s1)
        paypal_sync = PaypalSync.FAILED

    return CreatedShipment(
        shipment_id=shipment_id,
        order_id=cmd.order_id,
        status=ShipmentStatus.LABEL_CREATED,
        promised_at_sim=promised_at_sim,
        paypal_sync=paypal_sync,
        paypal_tracker_id=tracker_id,
        replayed=False,
    )


async def apply_transition(
    session: AsyncSession,
    shipment_id: UUID,
    to_status: ShipmentStatus,
    source: TransitionSource,
    occurred_at_sim: datetime,
    actor: str,
    note_code: str | None,
) -> AppliedTransition:
    """Validate against SHIPMENT_TRANSITIONS and apply one status change with CAS on version.

    Inputs: target status, source (SCRIPT|FORCE|MERCHANT), occurred_at_sim (= due_at_sim for
    scripts).
    Output: AppliedTransition after shipments.status/anomaly/version and shipment_events are
    written,
    plus outbox shipment.status_changed in the same transaction (spec s8, C3 for demo actions).
    Edge cases: illegal edge -> IllegalTransition (409 ILLEGAL_TRANSITION); LOST -> DELIVERED sets
    anomaly=LOST_THEN_DELIVERED; zero rows updated on CAS -> retry or conflict (caller decides).
    """
    shipment = await repo.get_shipment_for_update(session, shipment_id)
    if shipment is None:
        raise LookupError(f"shipment {shipment_id} not found")

    from_status = ShipmentStatus(shipment["status"])
    if not is_legal_transition(from_status, to_status, source):
        raise IllegalTransition(f"{from_status} -> {to_status} ({source}) is not legal")

    anomaly: Anomaly | None = None
    if (from_status, to_status) == DELIVERED_AFTER_LOST_EDGE:
        anomaly = Anomaly.LOST_THEN_DELIVERED
    elif (
        to_status == ShipmentStatus.DELIVERED
        and occurred_at_sim > shipment["promised_at_sim"]
    ):
        anomaly = Anomaly.DELIVERED_AFTER_PROMISE

    active = to_status not in (ShipmentStatus.DELIVERED, ShipmentStatus.CANCELLED)
    updated = await repo.update_shipment_status_cas(
        session,
        shipment_id=shipment_id,
        expected_version=shipment["version"],
        new_status=to_status.value,
        anomaly=anomaly.value if anomaly else None,
        active=active,
    )
    if not updated:
        raise LookupError(f"shipment {shipment_id} version changed concurrently")

    seq = await repo.next_shipment_event_seq(session, shipment_id)
    await repo.insert_shipment_event(
        session,
        shipment_id=shipment_id,
        seq=seq,
        from_status=from_status.value,
        to_status=to_status.value,
        source=source.value,
        occurred_at_sim=occurred_at_sim,
        actor=actor,
        note_code=note_code,
    )
    await repo.insert_outbox_event(
        session,
        event_id=uuid4(),
        event_type="shipment.status_changed",
        aggregate_id=str(shipment_id),
        payload={
            "shipment_id": str(shipment_id),
            "from_status": from_status.value,
            "to_status": to_status.value,
            "source": source.value,
            "occurred_at_sim": occurred_at_sim.isoformat(),
            "anomaly": anomaly.value if anomaly else None,
            "simulated": True,
        },
    )

    return AppliedTransition(
        shipment_id=shipment_id,
        seq=seq,
        from_status=from_status,
        to_status=to_status,
        source=source,
        occurred_at_sim=occurred_at_sim,
        anomaly=anomaly,
    )


async def cancel_shipment(
    session: AsyncSession,
    shipment_id: UUID,
    reason_code: str,
    actor_sub: str,
) -> PaypalSync:
    """Merchant cancel: move a non-terminal shipment to CANCELLED, then best-effort PayPal PATCH.

    Inputs: shipment id, reason enum, merchant sub. Output: resulting paypal_sync (CANCELLED or
    FAILED).
    Edge cases: DELIVERED or already CANCELLED -> IllegalTransition (409); PayPal PATCH is
    irreversible (V), so the local CANCELLED row is the truth even if PayPal fails (spec s1, s2).
    """
    shipment = await repo.get_shipment(session, shipment_id)
    if shipment is None:
        raise LookupError(f"shipment {shipment_id} not found")

    now = repo.now_utc()
    await apply_transition(
        session,
        shipment_id=shipment_id,
        to_status=ShipmentStatus.CANCELLED,
        source=TransitionSource.MERCHANT,
        occurred_at_sim=now,
        actor=actor_sub,
        note_code=reason_code,
    )
    await session.commit()

    paypal_sync = PaypalSync.CANCELLED
    tracker_id = shipment.get("paypal_tracker_id")
    if tracker_id:
        try:
            result = await clients.cancel_tracking(
                order_id=shipment["order_id"], tracker_id=tracker_id
            )
            paypal_sync = PaypalSync.CANCELLED if result.ok else PaypalSync.FAILED
        except Exception:  # noqa: BLE001 - PayPal PATCH failure never overrides local truth
            paypal_sync = PaypalSync.FAILED
        await repo.update_shipment_paypal_sync(
            session,
            shipment_id=shipment_id,
            paypal_tracker_id=tracker_id,
            paypal_sync=paypal_sync.value,
            paypal_last_error=None
            if paypal_sync == PaypalSync.CANCELLED
            else "cancel_tracking failed",
        )
        await session.commit()

    return paypal_sync
