"""Ops surface (freeze flag, demo mode, tick) - stubs per spec.md section 5.1 / 10."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Response

from app.deps import Principal, require_operator, require_session
from app.schemas.ops import FreezeRequest

router = APIRouter(prefix="/api/ops", tags=["ops"])


def _not_implemented(response: Response, path: str) -> dict:
    response.status_code = 501
    return {"error": "not_implemented", "detail": f"{path} pending Wave 5"}


@router.get("/status")
async def status(
    response: Response, principal: Principal = Depends(require_session)
) -> dict:
    return _not_implemented(response, "GET /api/ops/status")


@router.post("/freeze")
async def freeze(
    body: FreezeRequest,
    response: Response,
    principal: Principal = Depends(require_operator),
) -> dict:
    return _not_implemented(response, "POST /api/ops/freeze")


@router.post("/tick")
async def tick(
    response: Response, x_tick_secret: str | None = Header(default=None)
) -> dict:
    return _not_implemented(response, "POST /api/ops/tick")
