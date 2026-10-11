"""/internal/* -- api.md section 10. Never routed by the gateway.

Wave 4: validated stubs, 501.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.deps import Principal, require_service_jwt
from app.schemas.internal import InboundEvent

router = APIRouter(prefix="/internal", tags=["internal"])


def _not_implemented(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={"error": "not_implemented", "detail": detail, "request_id": None},
    )


@router.post("/events", status_code=501)
async def internal_events(
    body: InboundEvent,
    _principal: Principal = Depends(require_service_jwt),
) -> JSONResponse:
    return _not_implemented("POST /internal/events pending Wave 5")


@router.get("/outbox", status_code=501)
async def read_outbox(
    after: int = 0,
    _principal: Principal = Depends(require_service_jwt),
) -> JSONResponse:
    return _not_implemented("GET /internal/outbox pending Wave 5")


@router.post("/outbox/flush", status_code=501)
async def flush_outbox(_principal: Principal = Depends(require_service_jwt)) -> JSONResponse:
    return _not_implemented("POST /internal/outbox/flush pending Wave 5")


@router.post("/reconcile", status_code=501)
async def reconcile(_principal: Principal = Depends(require_service_jwt)) -> JSONResponse:
    return _not_implemented("POST /internal/reconcile pending Wave 5")
