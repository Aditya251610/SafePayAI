"""GET /healthz, /readyz - real in Wave 4, per conventions doc section 3.

mandate/api.md section 12 extends readyz to also report keys/migration_head/
trusted_issuers; Wave 4 keeps the shape but only truly checks DB connectivity
(key/migration checks are Wave 5 business logic).
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from app_mandate.db import ping

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "service": "mandate"}


@router.get("/readyz")
async def readyz(response: Response) -> dict:
    try:
        await ping()
    except Exception as exc:  # noqa: BLE001
        response.status_code = 503
        return {"status": "not_ready", "db": type(exc).__name__}
    return {"status": "ready", "db": "ok"}
