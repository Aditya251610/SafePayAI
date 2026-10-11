"""Internal event inbox/outbox + tick endpoints per resolution/api.md section 2.
Never routed by the gateway externally (404 externally is a gateway concern, not ours)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import require_internal_jwt, require_tick_secret
from app.schemas.cases import InternalEventEnvelope

router = APIRouter(prefix="/internal", tags=["internal"])


def _not_implemented(endpoint: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=f"{endpoint} pending Wave 5")


@router.post("/events", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def internal_events_receive(
    body: InternalEventEnvelope,
    claims: dict = Depends(require_internal_jwt),
) -> None:
    raise _not_implemented("POST /internal/events")


@router.get("/outbox", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def internal_outbox_pull(after: int = 0, claims: dict = Depends(require_internal_jwt)) -> None:
    raise _not_implemented("GET /internal/outbox")


@router.post("/outbox/flush", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def internal_outbox_flush(_: None = Depends(require_tick_secret)) -> None:
    raise _not_implemented("POST /internal/outbox/flush")


@router.post("/tick", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def internal_tick(_: None = Depends(require_tick_secret)) -> None:
    raise _not_implemented("POST /internal/tick")
