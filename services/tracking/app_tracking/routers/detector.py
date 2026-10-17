"""Detector + internal tick/event endpoints per tracking/api.md sections on
POST /detector/run, POST /internal/tick, POST /internal/events, GET /internal/events.

Wired to app/usecases/tick.py (Wave 5B). /detector/run and /internal/tick call the same
run_tick function (spec.md section 5, conflict C1).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app_tracking.db import get_session
from app_tracking.deps import require_internal_jwt, require_tick_secret
from app_tracking.schemas.shipments import DetectorRunResponse, InternalEventEnvelope
from app_tracking.usecases.tick import TickTrigger
from app_tracking.usecases.tick import run_tick as uc_run_tick

router = APIRouter(tags=["detector"])


def _not_implemented(endpoint: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=f"{endpoint} pending Wave 5"
    )


@router.post("/detector/run")
async def detector_run(
    claims: dict = Depends(require_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> DetectorRunResponse:
    result = await uc_run_tick(session, TickTrigger.MANUAL)
    return DetectorRunResponse(
        trigger=result.trigger.value,
        skipped_lease=result.skipped_lease,
        applied=result.applied_count,
        detected=result.detected_count,
        sim_now=result.sim_now.isoformat(),
    )


@router.post("/internal/tick")
async def internal_tick(
    _: None = Depends(require_tick_secret),
    session: AsyncSession = Depends(get_session),
) -> DetectorRunResponse:
    result = await uc_run_tick(session, TickTrigger.EXTERNAL)
    return DetectorRunResponse(
        trigger=result.trigger.value,
        skipped_lease=result.skipped_lease,
        applied=result.applied_count,
        detected=result.detected_count,
        sim_now=result.sim_now.isoformat(),
    )


@router.post("/internal/events", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def internal_events_receive(
    body: InternalEventEnvelope,
    claims: dict = Depends(require_internal_jwt),
) -> None:
    raise _not_implemented("POST /internal/events")


@router.get("/internal/events", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def internal_events_pull(
    after: int = 0, claims: dict = Depends(require_internal_jwt)
) -> None:
    raise _not_implemented("GET /internal/events")
