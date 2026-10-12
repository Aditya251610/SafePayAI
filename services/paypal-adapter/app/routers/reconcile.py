"""POST /v1/reconcile/{request_id} -- api.md section 4/6, spec.md section 6. Real as of the
refund_capture/MCP wave: an idempotent, read-only lookup against our own call_ledger by
request_id -- never calls PayPal again, never mutates state (api.md section 6: "caller rules:
NEVER blind-retry... call get_refund / get_capture / get_order or POST /reconcile/{request_id}
until final").

Any authenticated internal caller may reconcile (matches the Wave 4 stub's
`require_internal_jwt`, not a tool-specific allowlist entry -- resolution is the only caller
today, but there is no money/data exposure risk in a caller reading back its own request_id's
outcome).

`compat_router` mirrors captures.py/refunds.py's compat shim: resolution's already-merged
Wave 5B client (services/resolution/app/clients.py `reconcile_refund`) calls
`POST /reconcile/{request_id}` with no `/v1` prefix.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import ops
from app.db import get_db
from app.deps import Caller, require_internal_jwt

router = APIRouter(prefix="/v1", tags=["reconcile"])
compat_router = APIRouter(tags=["reconcile-compat"])

REQUEST_ID_PATTERN = r"^[0-9a-fA-F-]{36}$"


def _trace_id(request: Request) -> str:
    return request.headers.get("X-Trace-Id") or str(uuid.uuid4())


def _status_to_http(status: str, ok: bool) -> int:
    if ok:
        return 200
    mapping = {"IN_PROGRESS": 202, "UNKNOWN": 504, "REJECTED": 404}
    return mapping.get(status, 400)


async def _reconcile_handler(
    request: Request, request_id: str, session: AsyncSession
) -> JSONResponse:
    trace_id = _trace_id(request)
    try:
        envelope = await ops.reconcile(session, request_id, trace_id=trace_id)
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
    http_status = _status_to_http(envelope["status"], envelope["ok"])
    return JSONResponse(status_code=http_status, content=envelope)


@router.post("/reconcile/{request_id}")
async def reconcile(
    request: Request,
    request_id: str = Path(pattern=REQUEST_ID_PATTERN),
    _caller: Caller = Depends(require_internal_jwt),
    session: AsyncSession = Depends(get_db),
) -> JSONResponse:
    return await _reconcile_handler(request, request_id, session)


@compat_router.post("/reconcile/{request_id}")
async def reconcile_compat(
    request: Request,
    request_id: str = Path(pattern=REQUEST_ID_PATTERN),
    _caller: Caller = Depends(require_internal_jwt),
    session: AsyncSession = Depends(get_db),
) -> JSONResponse:
    return await _reconcile_handler(request, request_id, session)
