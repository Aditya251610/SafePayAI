"""Demo-clock simulator endpoints per tracking/api.md + spec.md section 8 (guards, sandbox-only).

Guard order (spec s8): SANDBOX_MODE -> DEMO_CONTROLS_ENABLED -> JWT merchant role -> body/header
checks -> rate limit -> bounds. Rate limiting is left to the gateway (not duplicated here);
bounds validation happens inside the usecase (ValueError -> 400).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import repo
from app.db import get_session
from app.deps import require_idempotency_key, require_internal_jwt
from app.domain.demo_clock import sim_now as compute_sim_now
from app.domain.shipment_states import IllegalTransition, ShipmentStatus
from app.schemas.shipments import (
    DemoClockAdvanceRequest,
    DemoClockAdvanceResponse,
    DemoClockResetRequest,
    DemoClockResetResponse,
    DemoClockResponse,
    DemoForceShipmentRequest,
    DemoForceShipmentResponse,
    TickSummary,
)
from app.settings import settings
from app.usecases.demo import DemoActor
from app.usecases.demo import advance_clock as uc_advance_clock
from app.usecases.demo import force_shipment as uc_force_shipment
from app.usecases.demo import reset_demo as uc_reset_demo

router = APIRouter(prefix="/demo", tags=["demo"])


def _not_implemented(endpoint: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=f"{endpoint} pending Wave 5"
    )


def _require_sandbox(claims: dict) -> None:
    """Guards per spec s8: sandbox flags + merchant role, in order, fail closed."""
    if not settings.sandbox_mode:
        raise HTTPException(status_code=404)
    if not settings.demo_controls_enabled:
        raise HTTPException(status_code=404)
    if (claims.get("act") or {}).get("role") != "merchant":
        raise HTTPException(status_code=403, detail="ROLE_NOT_ALLOWED")


@router.get("/clock")
async def get_clock(
    claims: dict = Depends(require_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> DemoClockResponse:
    clock_row = await repo.get_demo_clock_nolock(session)
    sim_now_val = compute_sim_now(repo.now_utc(), clock_row["offset_seconds"])
    return DemoClockResponse(sim_now=sim_now_val.isoformat())


@router.post("/clock/advance")
async def advance_clock(
    body: DemoClockAdvanceRequest,
    claims: dict = Depends(require_internal_jwt),
    idempotency_key: str = Depends(require_idempotency_key),
    session: AsyncSession = Depends(get_session),
) -> DemoClockAdvanceResponse:
    _require_sandbox(claims)
    actor = DemoActor(
        actor_sub=str(claims.get("sub", "")),
        role="merchant",
        trace_id=claims.get("trace_id"),
    )
    try:
        result, tick = await uc_advance_clock(
            session,
            body.delta_seconds,
            body.reason,
            idempotency_key,
            actor,
            settings.demo_max_advance_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DemoClockAdvanceResponse(
        from_sim=result.from_sim.isoformat(),
        to_sim=result.to_sim.isoformat(),
        version=result.version,
        tick=TickSummary(
            applied=tick.applied_count,
            detected=tick.detected_count,
            skipped_lease=tick.skipped_lease,
        ),
    )


@router.post("/clock/reset")
async def reset_clock(
    body: DemoClockResetRequest,
    claims: dict = Depends(require_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> DemoClockResetResponse:
    _require_sandbox(claims)
    actor = DemoActor(
        actor_sub=str(claims.get("sub", "")),
        role="merchant",
        trace_id=claims.get("trace_id"),
    )
    offset = await uc_reset_demo(session, body.reason, actor)
    return DemoClockResetResponse(offset_seconds=offset)


@router.post("/shipments/{shipment_id}/force")
async def force_shipment(
    shipment_id: str,
    body: DemoForceShipmentRequest,
    claims: dict = Depends(require_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> DemoForceShipmentResponse:
    import uuid as uuid_lib

    _require_sandbox(claims)
    actor = DemoActor(
        actor_sub=str(claims.get("sub", "")),
        role="merchant",
        trace_id=claims.get("trace_id"),
    )
    try:
        outcome = await uc_force_shipment(
            session,
            uuid_lib.UUID(shipment_id),
            ShipmentStatus(body.to_status),
            body.reason,
            actor,
        )
    except IllegalTransition as exc:
        raise HTTPException(status_code=409, detail="ILLEGAL_TRANSITION") from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="SHIPMENT_NOT_FOUND") from exc
    return DemoForceShipmentResponse(
        id=str(outcome.shipment_id),
        status=outcome.transition.to_status.value,
        tick=TickSummary(
            applied=outcome.tick.applied_count,
            detected=outcome.tick.detected_count,
            skipped_lease=outcome.tick.skipped_lease,
        ),
    )
