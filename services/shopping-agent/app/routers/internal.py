"""/internal/outbox/* -- api.md section 7. Never routed by the gateway.

Wave 4: stubs. Outbox relay logic is Wave 5.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.deps import ServicePrincipal, require_service_jwt

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/outbox/flush", status_code=501)
async def flush_outbox(
    _principal: ServicePrincipal = Depends(require_service_jwt),
) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={
            "error": "not_implemented",
            "detail": "POST /internal/outbox/flush pending Wave 5",
            "request_id": None,
        },
    )


@router.get("/outbox", status_code=501)
async def read_outbox(
    after: int = 0,
    _principal: ServicePrincipal = Depends(require_service_jwt),
) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={
            "error": "not_implemented",
            "detail": "GET /internal/outbox pending Wave 5",
            "request_id": None,
        },
    )
