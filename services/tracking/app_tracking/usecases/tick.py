"""Tick use cases: run one detector tick under the lease, and lazy per-shipment catch-up.

Implements tracking/spec.md section 5 (poller design: lease, triggers, idempotent ticks) and
section 4 (double-fire protection, apply due chain then evaluate). Every trigger calls run_tick.
Scaffold only; the bodies are yours to write. Transactions and row locks belong here, not in
domain/.
"""

from __future__ import annotations

import uuid as uuid_lib
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app_tracking import repo
from app_tracking.deps import mint_outbound_token
from app_tracking.domain.demo_clock import sim_now as compute_sim_now
from app_tracking.domain.detector import (
    DetectionThresholds,
    ShipmentFacts,
    evaluate_detections,
)
from app_tracking.domain.shipment_states import ShipmentStatus, TransitionSource
from app_tracking.settings import settings
from app_tracking.usecases.shipments import apply_transition

_LEASE_NAME = "detector"


def _thresholds() -> DetectionThresholds:
    return DetectionThresholds(
        late_grace_seconds=settings.late_grace_seconds,
        lost_after_seconds=settings.lost_after_seconds,
        lost_after_promise_seconds=settings.lost_after_promise_seconds,
    )


def _facts_from_row(row: dict, last_event_sim: datetime | None) -> ShipmentFacts:
    from app_tracking.domain.shipment_states import Anomaly

    return ShipmentFacts(
        shipment_id=row["id"],
        order_id=row["order_id"],
        capture_id=row["capture_id"] or "",
        mandate_id=row["mandate_id"] or "",
        status=ShipmentStatus(row["status"]),
        anomaly=Anomaly(row["anomaly"]) if row.get("anomaly") else None,
        active=row["active"],
        created_at_sim=row["created_at_sim"],
        promised_at_sim=row["promised_at_sim"],
        last_event_sim=last_event_sim,
        delivered_at_sim=None,
        version=row["version"],
    )


async def _materialize_full(
    session: AsyncSession, shipment_id: UUID, sim_now: datetime
) -> tuple[int, int, list[dict]]:
    """Apply the due scheduled-event chain, then evaluate detections. Returns (applied,
    detected, new_detection_events) -- the last is the payload list for notifying resolution
    after commit (resolution/api.md section 6 inbox: shipment.late_detected/lost_detected)."""
    applied = 0
    due_events = await repo.get_due_scheduled_events(session, shipment_id, sim_now)
    for event in due_events:
        won = await repo.mark_scheduled_event_applied(
            session,
            shipment_id=shipment_id,
            seq=event["seq"],
            applied_at=event["due_at_sim"],
            applied_by="tick",
        )
        if not won:
            continue  # someone else already applied it (spec s4 item 1 CAS)
        await apply_transition(
            session,
            shipment_id=shipment_id,
            to_status=ShipmentStatus(event["to_status"]),
            source=TransitionSource.SCRIPT,
            occurred_at_sim=event["due_at_sim"],
            actor="system",
            note_code=None,
        )
        applied += 1

    row = await repo.get_shipment(session, shipment_id)
    if row is None:
        return applied, 0, []
    last_event_sim = await repo.get_last_event_sim(session, shipment_id)
    facts = _facts_from_row(row, last_event_sim)

    detected = 0
    new_events: list[dict] = []
    for candidate in evaluate_detections(facts, sim_now, _thresholds()):
        inserted = await repo.insert_detection_if_absent(
            session,
            shipment_id=candidate.shipment_id,
            kind=candidate.kind.value,
            detected_at_sim=candidate.detected_at_sim,
            event_id=candidate.event_id,
        )
        if not inserted:
            continue
        detected += 1
        event_type = (
            "shipment.late_detected"
            if candidate.kind.value == "LATE"
            else "shipment.lost_detected"
        )
        payload = {
            "shipment_id": str(candidate.shipment_id),
            "order_id": facts.order_id,
            "capture_id": facts.capture_id,
            "mandate_id": facts.mandate_id,
            "kind": candidate.kind.value,
            "promised_at_sim": candidate.promised_at_sim.isoformat(),
            "detected_at_sim": candidate.detected_at_sim.isoformat(),
            "carrier_status": candidate.carrier_status.value,
            "anomaly": candidate.anomaly.value if candidate.anomaly else None,
            "simulated": True,
        }
        await repo.insert_outbox_event(
            session,
            event_id=candidate.event_id,
            event_type=event_type,
            aggregate_id=str(shipment_id),
            payload=payload,
        )
        new_events.append(
            {"event_id": candidate.event_id, "type": event_type, "payload": payload}
        )

    return applied, detected, new_events


async def _notify_resolution(new_events: list[dict]) -> None:
    """Best-effort push of newly-detected LATE/LOST events to resolution's inbox
    (resolution/api.md section 6). Never raises: the outbox row already persisted the
    event for later catch-up (ADR-003), so a failure here is not data loss, only a
    delayed automated case open -- resolution's own reconcile/manual paths still work."""
    if not settings.resolution_url or not new_events:
        return
    token = mint_outbound_token("resolution")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(
        base_url=settings.resolution_url, timeout=httpx.Timeout(5.0)
    ) as client:
        for event in new_events:
            try:
                await client.post(
                    "/internal/events",
                    json={
                        "event_id": str(event["event_id"]),
                        "type": event["type"],
                        "version": 1,
                        "aggregate_id": event["payload"]["shipment_id"],
                        "payload": event["payload"],
                    },
                    headers=headers,
                )
            except httpx.HTTPError:
                continue


class TickTrigger(StrEnum):
    """Who asked for the tick; stored on detector_runs.trigger (spec s5, api.md POST
    /detector/run)."""

    MANUAL = "manual"
    INPROCESS = "inprocess"
    PING = "ping"
    EXTERNAL = "external"


@dataclass(frozen=True, slots=True)
class TickResult:
    """Response body of POST /detector/run and /internal/tick (api.md)."""

    trigger: TickTrigger
    skipped_lease: bool
    applied_count: int
    detected_count: int
    sim_now: datetime


async def acquire_tick_lease(
    session: AsyncSession, holder: str, ttl_seconds: int
) -> bool:
    """Try to take the named tick lease with INSERT ... ON CONFLICT ... WHERE expires_at < now().

    Inputs: session, holder id for this process, TTL from PS_TRACKING_TICK_LEASE_SECONDS.
    Output: True if acquired; False means skipped_lease=true for the caller.
    Edge cases: uses DB now(), never the demo clock (spec s5); a crashed holder expires on its own.
    """
    return await repo.try_acquire_lease(
        session, name=_LEASE_NAME, holder=holder, ttl_seconds=ttl_seconds
    )


async def run_tick(session: AsyncSession, trigger: TickTrigger) -> TickResult:
    """Run one idempotent tick: lease, apply due scheduled events, evaluate rules, flush outbox.

    Inputs: session and trigger. Output: TickResult with counts (applied, detected).
    Edge cases: lease held elsewhere -> skipped_lease=True, no work; safe to call any number of
    times;
    a late tick yields the same events with a later detected_at_real (spec s5 missed ticks).
    """
    holder = f"{trigger.value}-{uuid_lib.uuid4()}"
    clock_row = await repo.get_demo_clock_nolock(session)
    current_sim_now = compute_sim_now(repo.now_utc(), clock_row["offset_seconds"])

    acquired = await acquire_tick_lease(session, holder, settings.tick_lease_seconds)
    if not acquired:
        await session.commit()
        return TickResult(
            trigger=trigger,
            skipped_lease=True,
            applied_count=0,
            detected_count=0,
            sim_now=current_sim_now,
        )

    run_id = await repo.insert_detector_run(
        session, trigger=trigger.value, started_at=repo.now_utc(), skipped_lease=False
    )

    applied_total = 0
    detected_total = 0
    all_new_events: list[dict] = []
    shipments = await repo.get_active_nonterminal_shipments(session)
    for shipment in shipments:
        applied, detected, new_events = await _materialize_full(
            session, shipment["id"], current_sim_now
        )
        applied_total += applied
        detected_total += detected
        all_new_events.extend(new_events)

    await repo.finish_detector_run(
        session,
        run_id=run_id,
        applied_count=applied_total,
        detected_count=detected_total,
    )
    await session.commit()
    await _notify_resolution(all_new_events)

    return TickResult(
        trigger=trigger,
        skipped_lease=False,
        applied_count=applied_total,
        detected_count=detected_total,
        sim_now=current_sim_now,
    )


async def materialize_shipment(
    session: AsyncSession, shipment_id: UUID, sim_now: datetime
) -> int:
    """Apply due scheduled events and evaluate rules for ONE shipment under its row lock.

    Inputs: session, shipment id, current sim_now.
    Output: number of scheduled events applied.
    Edge cases: called before every GET /shipments/* and every resolution call (spec s5 item 3);
    events apply in seq order with occurred_at_sim = due_at_sim (spec s4 item 1). Caller is
    responsible for committing before any new detections are notified to resolution (see
    callers in routers/shipments.py).
    """
    applied, _detected, new_events = await _materialize_full(
        session, shipment_id, sim_now
    )
    if new_events:
        await session.commit()
        await _notify_resolution(new_events)
    return applied
