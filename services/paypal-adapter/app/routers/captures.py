"""GET /v1/captures/{id}, POST /v1/captures/{id}/refund -- api.md section 4/5.4/5.7.

refund_capture (not create_refund, per the confirmed rename) is real as of Wave 5B/paypal-
adapter-refund-mcp: real PayPal call via app.ops, backed by the call_ledger/refund_ledger
idempotency flow. get_capture stays a Wave 4 501 stub -- out of this task's scope.

`compat_router` registers the same refund_capture handler at the bare path (no `/v1` prefix)
to match resolution's already-merged Wave 5B client (services/resolution/app/clients.py
`refund_capture` calls `POST /captures/{capture_id}/refund`, not `/v1/captures/...`) --
api.md section 4 says "all under /v1"; this is a documented, deliberate compat shim rather
than a spec change, so both paths work until resolution's client or the spec is reconciled.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import ops
from app.db import get_db
from app.deps import Caller, require_tool_permission
from app.paypal_client import PayPalClient, get_paypal_client
from app.schemas.envelope import not_implemented_envelope
from app.schemas.orders import RefundCaptureRequest
from app.settings import Settings, get_settings

router = APIRouter(prefix="/v1", tags=["captures"])
compat_router = APIRouter(tags=["captures-compat"])

_require_refund_capture = require_tool_permission("refund_capture")


def _trace_id(request: Request) -> str:
    return request.headers.get("X-Trace-Id") or str(uuid.uuid4())


def _status_to_http(status: str, ok: bool) -> int:
    if ok:
        return 201 if status == "OK" else 200
    mapping = {"IN_PROGRESS": 202, "UNKNOWN": 504, "REJECTED": 400}
    return mapping.get(status, 400)


@router.get("/captures/{capture_id}", status_code=501)
async def get_capture(
    capture_id: str,
    _caller: Caller = Depends(require_tool_permission("get_capture")),  # noqa: B008
) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=not_implemented_envelope("get_capture pending Wave 5", str(uuid.uuid4())),
    )


async def _refund_capture_handler(
    request: Request,
    capture_id: str,
    body: RefundCaptureRequest,
    caller: Caller,
    x_authorization_ticket: str | None,
    session: AsyncSession,
    settings: Settings,
    client: PayPalClient,
) -> JSONResponse:
    trace_id = _trace_id(request)
    ticket = x_authorization_ticket or body.ticket
    if not ticket:
        raise HTTPException(status_code=403, detail="TICKET_INVALID")
    try:
        envelope = await ops.refund_capture(
            session,
            client,
            settings,
            caller=caller.sub,
            capture_id=capture_id,
            request_id=body.request_id,
            invoice_id=body.invoice_id,
            amount_minor=body.amount_minor,
            currency=body.currency,
            ticket=ticket,
            trace_id=trace_id,
        )
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


@router.post("/captures/{capture_id}/refund")
async def refund_capture(
    request: Request,
    capture_id: str,
    body: RefundCaptureRequest,
    caller: Caller = Depends(_require_refund_capture),
    x_authorization_ticket: str | None = Header(default=None, alias="X-Authorization-Ticket"),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    client: PayPalClient = Depends(get_paypal_client),
) -> JSONResponse:
    return await _refund_capture_handler(
        request, capture_id, body, caller, x_authorization_ticket, session, settings, client
    )


@compat_router.post("/captures/{capture_id}/refund")
async def refund_capture_compat(
    request: Request,
    capture_id: str,
    body: RefundCaptureRequest,
    caller: Caller = Depends(_require_refund_capture),
    x_authorization_ticket: str | None = Header(default=None, alias="X-Authorization-Ticket"),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    client: PayPalClient = Depends(get_paypal_client),
) -> JSONResponse:
    return await _refund_capture_handler(
        request, capture_id, body, caller, x_authorization_ticket, session, settings, client
    )
