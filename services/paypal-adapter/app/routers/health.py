"""GET /healthz, /readyz, /health (alias, C8) -- real in Wave 4, unauthenticated, no secrets.

Per docs/service-skeleton-conventions.md section 3 and paypal-adapter/deployment.md section 4.
No PayPal call from either (healthz "cheap enough to survive being a wake-up probe").
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import get_session_factory
from app.settings import get_settings

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


def _sandbox_guard_pass() -> bool:
    settings = get_settings()
    if settings.paypal_mode != "sandbox":
        return False
    if not settings.paypal_base_url.startswith("https://api-m.sandbox.paypal.com"):
        return False
    return True


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health")
async def health_alias() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz() -> JSONResponse:
    db_ok = await _check_db(get_session_factory())
    guard_ok = _sandbox_guard_pass()
    body = {
        "db": "ok" if db_ok else "unreachable",
        "sandbox_guard": "pass" if guard_ok else "fail",
    }
    status_code = 200 if (db_ok and guard_ok) else 503
    return JSONResponse(status_code=status_code, content=body)
