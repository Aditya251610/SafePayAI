"""Health/readiness routes. REAL in Wave 4 (conventions doc section 3).

resolution's own spec.md section 15 conflict C8 already resolves the /healthz vs /health
naming question in-doc: implement /healthz, /readyz, and add /health, /health/deep aliases.
No conflict with the conventions doc here (both name /health + /readyz as canonical and
allow this service's documented aliases).
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.db import ping_db
from app.schemas.common import HealthResponse, ReadyResponse

router = APIRouter(tags=["health"])

SERVICE_NAME = "resolution"


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


@router.get("/health/deep", response_model=ReadyResponse)
async def health_deep(response: Response) -> ReadyResponse:
    # Wave 4: alias of readyz; real "flag readable" dependency check is Wave 5.
    return await readyz(response)
