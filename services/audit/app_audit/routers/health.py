"""GET /healthz and GET /readyz -- api.md sec 6, service-skeleton-conventions.md sec 3.

These are the only two routes in this service that are real in Wave 4. /healthz never
touches the DB (protects Neon CU-hours, deployment.md sec 3/5); /readyz does a bounded
SELECT 1 with retry/backoff.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app_audit.db import check_db_ready

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "audit"}


@router.get("/readyz")
async def readyz() -> JSONResponse:
    ok, error_class = await check_db_ready()
    if ok:
        return JSONResponse(status_code=200, content={"status": "ready", "db": "ok"})
    return JSONResponse(
        status_code=503,
        content={"status": "not_ready", "db": error_class or "unknown_error"},
    )
