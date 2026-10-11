"""GET /healthz, GET /readyz -- real in Wave 4, per
docs/service-skeleton-conventions.md section 3 and api.md section 2/10.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import SessionLocal

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


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz() -> JSONResponse:
    db_ok = await _check_db(SessionLocal)
    body = {
        "db": "ok" if db_ok else "unreachable",
        "mandate": "unreachable",
        "catalog": "unreachable",
        "adapter": "unreachable",
    }
    return JSONResponse(status_code=200 if db_ok else 503, content=body)
