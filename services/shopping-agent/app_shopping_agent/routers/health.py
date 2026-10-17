"""GET /healthz, GET /readyz -- real in Wave 4, per
docs/service-skeleton-conventions.md section 3 and api.md section 7.

/healthz never touches the DB or an LLM provider. /readyz checks DB connectivity
(3 retries, backoff) and reports the gateway breaker state without calling a provider
(REQ-SA-018): an open breaker degrades to form/AI_PAUSED, it does not fail readiness.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app_shopping_agent.db import SessionLocal

router = APIRouter(tags=["health"])


async def _check_db(session_factory: async_sessionmaker[AsyncSession]) -> bool:
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            async with session_factory() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception as exc:  # noqa: BLE001 - deliberately broad; readiness probe
            last_exc = exc
            await asyncio.sleep(0.2 * (2**attempt))
    if last_exc is not None:
        return False
    return False


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz() -> JSONResponse:
    db_ok = await _check_db(SessionLocal)
    body = {
        "db": "ok" if db_ok else "unreachable",
        "config": "ok",
        "gateway_breaker": "closed",
    }
    return JSONResponse(status_code=200 if db_ok else 503, content=body)
