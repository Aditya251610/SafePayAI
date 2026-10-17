"""Health/readiness routes. These are REAL in Wave 4 (conventions doc section 3), not stubs.

tracking's own api.md/spec.md name these /healthz, /readyz, /healthz/deep (see spec.md
section 12 note and conventions-conflict flagged in the scaffolding report). We implement
the conventions doc's canonical /health + /readyz and add /healthz, /healthz/deep as
aliases so both naming conventions resolve.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app_tracking.db import ping_db
from app_tracking.schemas.common import HealthResponse, ReadyResponse

router = APIRouter(tags=["health"])

SERVICE_NAME = "tracking"


@router.get("/health", response_model=HealthResponse)
@router.get("/healthz", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service=SERVICE_NAME)


@router.get("/readyz", response_model=ReadyResponse)
async def readyz(response: Response) -> ReadyResponse:
    ok = await ping_db()
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadyResponse(status="not_ready", db="unreachable")
    return ReadyResponse(status="ready", db="ok")


@router.get("/healthz/deep", response_model=ReadyResponse)
async def healthz_deep(response: Response) -> ReadyResponse:
    # Wave 4: alias of readyz; real tick-triggering keep-warm behavior is Wave 5.
    return await readyz(response)
