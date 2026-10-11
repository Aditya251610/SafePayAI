"""GET /healthz, /readyz - real in Wave 4, per conventions doc section 3.

api-gateway/api.md section 3 also documents `?deep=true` upstream fan-out and a
`signing_key` field; Wave 4 keeps the shallow shape (DB ping only) and leaves the
deep/upstream fan-out for Wave 5.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from app.db import ping

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "service": "api-gateway"}


@router.get("/readyz")
async def readyz(response: Response) -> dict:
    try:
        await ping()
    except Exception as exc:  # noqa: BLE001
        response.status_code = 503
        return {"status": "not_ready", "db": type(exc).__name__}
    return {"status": "ready", "db": "ok"}
