"""Detector + internal tick/event endpoints per tracking/api.md sections on
POST /detector/run, POST /internal/tick, POST /internal/events, GET /internal/events.

Wave 4: stubs. The poller/lease/tick design (spec.md section 5) is Wave 5.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import require_internal_jwt, require_tick_secret
from app.schemas.shipments import InternalEventEnvelope

router = APIRouter(tags=["detector"])


def _not_implemented(endpoint: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=f"{endpoint} pending Wave 5")


@router.post("/detector/run", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def detector_run(claims: dict = Depends(require_internal_jwt)) -> None:
    raise _not_implemented("POST /detector/run")


@router.post("/internal/tick", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def internal_tick(_: None = Depends(require_tick_secret)) -> None:
    raise _not_implemented("POST /internal/tick")


@router.post("/internal/events", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def internal_events_receive(
    body: InternalEventEnvelope,
    claims: dict = Depends(require_internal_jwt),
) -> None:
    raise _not_implemented("POST /internal/events")


@router.get("/internal/events", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def internal_events_pull(after: int = 0, claims: dict = Depends(require_internal_jwt)) -> None:
    raise _not_implemented("GET /internal/events")
