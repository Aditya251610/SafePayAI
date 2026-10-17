"""GET /health, /healthz, /readyz - real in Wave 4, per conventions doc section 3.

catalog's own api.md additionally lists a bare `/health` alias of `/healthz`
(deployment doc naming, spec C5) - implemented here too.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from app_catalog.db import ping

router = APIRouter(tags=["health"])


@router.get("/health")
@router.get("/healthz")
async def health() -> dict:
    return {"status": "ok", "service": "catalog"}


@router.get("/readyz")
async def readyz(response: Response) -> dict:
    try:
        await ping()
    except Exception as exc:  # noqa: BLE001 - deliberately broad, mapped to 503 below
        response.status_code = 503
        return {"status": "not_ready", "db": type(exc).__name__}
    return {"status": "ready", "db": "ok"}
