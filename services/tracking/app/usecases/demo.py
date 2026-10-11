"""Demo-simulator use cases: clock advance, clock reset, and forced shipment status.

Implements tracking/spec.md section 3 (advance = CAS + clock_jumps row + synchronous tick), section
8
(guard order and audit via demo.action_performed) and api.md /demo/* endpoints. The HTTP guards
(SANDBOX_MODE, DEMO_CONTROLS_ENABLED, merchant role) are enforced in the router before these run.
Scaffold only; bodies are yours to write.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app import repo
from app.domain.demo_clock import (
    ClockAdvanceResult,
    DemoClockSnapshot,
    apply_advance,
    validate_advance_delta,
)
from app.domain.demo_clock import (
    sim_now as compute_sim_now,
)
from app.domain.shipment_states import ShipmentStatus, TransitionSource
from app.usecases.shipments import AppliedTransition, apply_transition
from app.usecases.tick import TickResult, TickTrigger, run_tick


@dataclass(frozen=True, slots=True)
class DemoActor:
    """Caller identity for audit (spec s8 demo.action_performed payload fields)."""

    actor_sub: str
    role: str  # always "merchant" (spec C2)
    trace_id: str | None


@dataclass(frozen=True, slots=True)
class ForceOutcome:
    """Result of POST /demo/shipments/{id}/force (api.md 200 body)."""

    shipment_id: UUID
    transition: AppliedTransition
    tick: TickResult


async def advance_clock(
    session: AsyncSession,
    delta_seconds: int,
    reason: str,
    idempotency_key: str,
    actor: DemoActor,
    max_advance_seconds: int,
) -> tuple[ClockAdvanceResult, TickResult]:
    """Move demo time forward by delta_seconds, record clock_jumps, then run a synchronous tick.

    Inputs: validated delta, reason code, Idempotency-Key, caller identity, configured max.
    Output: (ClockAdvanceResult, TickResult) for the 200 body.
    Edge cases: same Idempotency-Key replays the stored result (spec s3); version CAS mismatch ->
    409 CLOCK_VERSION_CONFLICT; delta out of bounds -> 400; audit row + outbox demo.action_performed
    written in the same tx; if the outbox insert fails the action fails (spec s8).
    """
    existing_jump = await repo.get_clock_jump_by_key(session, idempotency_key)
    if existing_jump is not None:
        tick = await run_tick(session, TickTrigger.MANUAL)
        return (
            ClockAdvanceResult(
                from_sim=existing_jump["from_sim"],
                to_sim=existing_jump["to_sim"],
                version=0,
            ),
            tick,
        )

    validate_advance_delta(delta_seconds, max_advance_seconds)

    clock_row = await repo.get_demo_clock(session)
    snapshot = DemoClockSnapshot(
        offset_seconds=clock_row["offset_seconds"], version=clock_row["version"]
    )
    now_real = repo.now_utc()
    from_sim = compute_sim_now(now_real, snapshot.offset_seconds)

    new_snapshot = apply_advance(snapshot, delta_seconds)
    updated = await repo.update_demo_clock_cas(
        session,
        new_offset=new_snapshot.offset_seconds,
        expected_version=snapshot.version,
    )
    if not updated:
        raise ValueError("CLOCK_VERSION_CONFLICT")

    to_sim = compute_sim_now(now_real, new_snapshot.offset_seconds)
    await repo.insert_clock_jump(
        session,
        idempotency_key=idempotency_key,
        from_sim=from_sim,
        to_sim=to_sim,
        actor=actor.actor_sub,
        reason=reason,
    )
    await repo.insert_outbox_event(
        session,
        event_id=uuid4(),
        event_type="demo.action_performed",
        aggregate_id="demo-clock",
        payload={
            "actor_sub": actor.actor_sub,
            "role": actor.role,
            "action": "CLOCK_ADVANCE",
            "target": "demo_clock",
            "before": from_sim.isoformat(),
            "after": to_sim.isoformat(),
            "reason": reason,
            "idempotency_key": idempotency_key,
            "sandbox_mode": True,
            "trace_id": actor.trace_id,
        },
    )

    # Advance is a single DB transaction (spec s3); the synchronous tick runs AFTER commit so
    # its own detections/outbox rows land in a fresh transaction.
    await session.commit()
    tick = await run_tick(session, TickTrigger.MANUAL)

    return ClockAdvanceResult(
        from_sim=from_sim, to_sim=to_sim, version=new_snapshot.version
    ), tick


async def reset_demo(
    session: AsyncSession,
    reason: str,
    actor: DemoActor,
) -> int:
    """Reset demo offset to 0 and reset scripted events/detections for demo=true shipments only.

    Inputs: reason, caller identity. Output: new offset_seconds (always 0 on success).
    Edge cases: real-sandbox (demo=false) shipments are untouched (spec s3, I); audited like
    advance.
    """
    # Reset clears detections for demo=true shipments so the detector can re-fire after the
    # clock rewinds (spec s3). Judgment call (I): this does NOT re-open already-applied
    # scheduled_events (their applied_at stays set), since spec s3 only requires forward-only
    # time outside of reset and doesn't specify replaying carrier scans from t0; a full replay
    # would need new scheduled_events rows, which is out of scope for a demo reset button.
    for shipment_id in await repo.get_demo_shipment_ids(session):
        await repo.delete_detections_for_shipment(session, shipment_id)

    await repo.reset_demo_clock(session)
    await repo.insert_outbox_event(
        session,
        event_id=uuid4(),
        event_type="demo.action_performed",
        aggregate_id="demo-clock",
        payload={
            "actor_sub": actor.actor_sub,
            "role": actor.role,
            "action": "CLOCK_RESET",
            "target": "demo_clock",
            "before": None,
            "after": 0,
            "reason": reason,
            "idempotency_key": None,
            "sandbox_mode": True,
            "trace_id": actor.trace_id,
        },
    )
    await session.commit()
    return 0


async def force_shipment(
    session: AsyncSession,
    shipment_id: UUID,
    to_status: ShipmentStatus,
    reason: str,
    actor: DemoActor,
) -> ForceOutcome:
    """Force a shipment to the next status along an allowed edge, source=FORCE, then tick.

    Inputs: shipment id, target status, reason, caller identity.
    Output: ForceOutcome with the applied transition and the tick result.
    Edge cases: illegal edge -> 409 ILLEGAL_TRANSITION; shipment owned by another merchant and not
    demo=true -> 403; forced LOST is still only a signal (resolution policy still applies, threat
    T6).
    """
    clock_row = await repo.get_demo_clock_nolock(session)
    sim_now_val = compute_sim_now(repo.now_utc(), clock_row["offset_seconds"])

    transition = await apply_transition(
        session,
        shipment_id=shipment_id,
        to_status=to_status,
        source=TransitionSource.FORCE,
        occurred_at_sim=sim_now_val,
        actor=actor.actor_sub,
        note_code=reason,
    )
    await repo.insert_outbox_event(
        session,
        event_id=uuid4(),
        event_type="demo.action_performed",
        aggregate_id=str(shipment_id),
        payload={
            "actor_sub": actor.actor_sub,
            "role": actor.role,
            "action": "SHIPMENT_FORCE",
            "target": str(shipment_id),
            "before": transition.from_status.value if transition.from_status else None,
            "after": transition.to_status.value,
            "reason": reason,
            "idempotency_key": None,
            "sandbox_mode": True,
            "trace_id": actor.trace_id,
        },
    )
    await session.commit()

    tick = await run_tick(session, TickTrigger.MANUAL)
    return ForceOutcome(shipment_id=shipment_id, transition=transition, tick=tick)
