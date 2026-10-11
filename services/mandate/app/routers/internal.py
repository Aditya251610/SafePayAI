"""Internal/cron endpoints - stubs per mandate/api.md section 12.

Guarded by INTERNAL_TICK_SECRET (shared bare name, conventions doc section 2).
Never routed by the gateway (404 externally); kept here for the service's own
standalone operation and for CI/cron calls.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Response

from app.settings import get_bare_secrets

router = APIRouter(prefix="/internal", tags=["internal"])


def _require_tick_secret(x_tick_secret: str | None) -> None:
    secrets = get_bare_secrets()
    if not secrets.internal_tick_secret or x_tick_secret != secrets.internal_tick_secret:
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")


@router.post("/sweep")
async def sweep(response: Response, x_tick_secret: str | None = Header(default=None)) -> dict:
    _require_tick_secret(x_tick_secret)
    response.status_code = 501
    return {"error": "not_implemented", "detail": "POST /internal/sweep pending Wave 5"}


@router.get("/outbox")
async def outbox_pull(response: Response, after: int = 0) -> dict:
    response.status_code = 501
    return {"error": "not_implemented", "detail": "GET /internal/outbox pending Wave 5"}


@router.post("/outbox/flush")
async def outbox_flush(response: Response, x_tick_secret: str | None = Header(default=None)) -> dict:
    _require_tick_secret(x_tick_secret)
    response.status_code = 501
    return {"error": "not_implemented", "detail": "POST /internal/outbox/flush pending Wave 5"}
