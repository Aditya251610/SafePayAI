"""GET /healthz, GET /readyz -- real in Wave 4, per
docs/service-skeleton-conventions.md section 3 and api.md section 2/10.
"""

from __future__ import annotations

import asyncio

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from safepayai_common.http.client import build_client
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app_checkout.db import SessionLocal
from app_checkout.settings import Settings, get_settings

router = APIRouter(tags=["health"])


async def _check_db(session_factory: async_sessionmaker[AsyncSession]) -> bool:
    for attempt in range(3):
        try:
            async with session_factory() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception:  # noqa: BLE001 - readiness probe, deliberately broad
            await asyncio.sleep(0.2 * (2**attempt))
    return False


async def _check_upstream(base_url: str) -> bool:
    """A readiness-probe check, not a business call: short timeout, no retry, any
    failure (timeout/connection/non-2xx) just means "not ready yet", not an error to
    surface to the caller."""
    try:
        async with build_client(base_url, timeout=httpx.Timeout(3.0)) as client:
            resp = await client.get("/healthz")
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(settings: Settings = Depends(get_settings)) -> JSONResponse:
    db_ok, mandate_ok, catalog_ok, adapter_ok = await asyncio.gather(
        _check_db(SessionLocal),
        _check_upstream(settings.mandate_base_url),
        _check_upstream(settings.catalog_base_url),
        _check_upstream(settings.paypal_adapter_base_url),
    )
    body = {
        "db": "ok" if db_ok else "unreachable",
        "mandate": "ok" if mandate_ok else "unreachable",
        "catalog": "ok" if catalog_ok else "unreachable",
        "adapter": "ok" if adapter_ok else "unreachable",
    }
    # Only db gates the status code (matches prior behavior/api.md): the upstreams are
    # advisory here, checked at actual call time by app/clients.py's own fail-closed
    # UpstreamError handling, not something readyz should 503 the whole service over.
    return JSONResponse(status_code=200 if db_ok else 503, content=body)
