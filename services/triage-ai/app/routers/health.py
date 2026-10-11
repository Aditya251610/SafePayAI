"""Health/readiness routes. REAL in Wave 4 (conventions doc section 3).

triage-ai's own api.md section 4 / deployment.md section 5 name /healthz, /readyz, /health,
/health/deep explicitly as aliases of each other — no conflict with the conventions doc's
canonical /health + /readyz naming. /health/deep additionally reports kill-switch and
breaker state for llm-gateway without a live model call; Wave 4 reports only the inert
settings flag (real breaker/budget state is Wave 5).
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.db import ping_db
from app.schemas.common import HealthResponse, ReadyResponse
from app.settings import settings

router = APIRouter(tags=["health"])

SERVICE_NAME = "triage-ai"


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
    # Wave 4: alias of readyz; real llm-gateway kill-switch/breaker reporting is Wave 5.
    _ = settings.llm_enabled
    return await readyz(response)
