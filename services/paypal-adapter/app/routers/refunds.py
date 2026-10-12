"""GET /v1/refunds/{id} -- api.md section 4/5.8. Real as of the refund_capture/MCP wave:
reads our own refund_ledger first (fast path), falls back to a live PayPal lookup.

`compat_router` mirrors captures.py's compat shim: resolution's already-merged Wave 5B
client (services/resolution/app/clients.py `get_refund`) calls `GET /refunds/{refund_id}`
with no `/v1` prefix.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import ops
from app.db import get_db
from app.deps import Caller, require_tool_permission
from app.paypal_client import PayPalClient, get_paypal_client

router = APIRouter(prefix="/v1", tags=["refunds"])
compat_router = APIRouter(tags=["refunds-compat"])

_require_get_refund = require_tool_permission("get_refund")


def _trace_id(request: Request) -> str:
    return request.headers.get("X-Trace-Id") or str(uuid.uuid4())


async def _get_refund_handler(
    request: Request,
    refund_id: str,
    session: AsyncSession,
    client: PayPalClient,
) -> JSONResponse:
    trace_id = _trace_id(request)
    try:
        envelope = await ops.get_refund(session, client, refund_id, trace_id=trace_id)
    except ops.OpError as exc:
        return JSONResponse(
            status_code=exc.http_status,
            content={
                "ok": False,
                "status": exc.status,
                "paypal_http_status": None,
                "data": None,
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "retryable": exc.retryable,
                    "paypal_name": None,
                },
                "replayed": False,
                "trace_id": trace_id,
            },
        )
    return JSONResponse(status_code=200, content=envelope)


@router.get("/refunds/{refund_id}")
async def get_refund(
    request: Request,
    refund_id: str,
    _caller: Caller = Depends(_require_get_refund),
    session: AsyncSession = Depends(get_db),
    client: PayPalClient = Depends(get_paypal_client),
) -> JSONResponse:
    return await _get_refund_handler(request, refund_id, session, client)


@compat_router.get("/refunds/{refund_id}")
async def get_refund_compat(
    request: Request,
    refund_id: str,
    _caller: Caller = Depends(_require_get_refund),
    session: AsyncSession = Depends(get_db),
    client: PayPalClient = Depends(get_paypal_client),
) -> JSONResponse:
    return await _get_refund_handler(request, refund_id, session, client)
