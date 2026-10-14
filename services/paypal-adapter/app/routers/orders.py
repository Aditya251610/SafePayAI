"""POST /v1/orders, GET /v1/orders/{id}, POST /v1/orders/{id}/capture -- api.md section 4/5.1-5.3.

Wave 5B (S1-08): real PayPal calls via app.ops, backed by app.paypal_client (token cache +
401 retry) and the call_ledger idempotency flow. Full authorization-ticket HMAC
verification (spec.md section 5) is now real: require_authorization_ticket still checks
the header is present (fast 403 for a missing ticket before any body processing), then each
handler calls deps.verify_authorization_ticket with the real request body fields (mandate_id,
proposal_hash, amount_minor, currency) once the body is parsed.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import ops
from app.db import get_db
from app.deps import (
    Caller,
    require_authorization_ticket,
    require_tool_permission,
    verify_authorization_ticket,
)
from app.paypal_client import PayPalClient, get_paypal_client
from app.schemas.orders import CaptureOrderRequest, CreateOrderRequest
from app.settings import Settings, get_settings

router = APIRouter(prefix="/v1", tags=["orders"])

# Module-level dependency callables (not called inline in a default, ruff B008): each
# `require_tool_permission(tool)` call happens once at import time, matching the
# pre-existing Wave 4 pattern across this service's other routers.
_require_create_order = require_tool_permission("create_order")
_require_get_order = require_tool_permission("get_order")
_require_capture_order = require_tool_permission("capture_order")


def _trace_id(request: Request) -> str:
    return request.headers.get("X-Trace-Id") or str(uuid.uuid4())


def _status_to_http(status: str, ok: bool) -> int:
    if ok:
        return 201 if status == "OK" else 200
    mapping = {"IN_PROGRESS": 202, "UNKNOWN": 504, "REJECTED": 400}
    return mapping.get(status, 400)


@router.post("/orders")
async def create_order(
    request: Request,
    body: CreateOrderRequest,
    caller: Caller = Depends(_require_create_order),
    ticket: str = Depends(require_authorization_ticket),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    client: PayPalClient = Depends(get_paypal_client),
) -> JSONResponse:
    trace_id = _trace_id(request)
    verify_authorization_ticket(
        ticket,
        caller_sub=caller.sub,
        mandate_id=body.mandate_id,
        proposal_hash=body.proposal_hash,
        amount_minor=body.amount_minor,
        currency=body.currency,
        settings=settings,
    )
    try:
        envelope = await ops.create_order(
            session,
            client,
            settings,
            caller=caller.sub,
            request_id=body.request_id,
            mandate_id=body.mandate_id,
            internal_order_id=body.internal_order_id,
            amount_minor=body.amount_minor,
            currency=body.currency,
            return_url=body.return_url,
            cancel_url=body.cancel_url,
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


@router.get("/orders/{order_id}")
async def get_order(
    request: Request,
    order_id: str,
    _caller: Caller = Depends(_require_get_order),
    client: PayPalClient = Depends(get_paypal_client),
) -> JSONResponse:
    trace_id = _trace_id(request)
    try:
        envelope = await ops.get_order(client, order_id, trace_id=trace_id)
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


@router.post("/orders/{order_id}/capture")
async def capture_order(
    request: Request,
    order_id: str,
    body: CaptureOrderRequest,
    caller: Caller = Depends(_require_capture_order),
    ticket: str = Depends(require_authorization_ticket),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    client: PayPalClient = Depends(get_paypal_client),
) -> JSONResponse:
    trace_id = _trace_id(request)
    verify_authorization_ticket(
        ticket,
        caller_sub=caller.sub,
        mandate_id=body.mandate_id,
        proposal_hash=body.proposal_hash,
        amount_minor=body.amount_minor,
        currency=body.currency,
        settings=settings,
    )
    try:
        envelope = await ops.capture_order(
            session,
            client,
            settings,
            caller=caller.sub,
            order_id=order_id,
            request_id=body.request_id,
            mandate_id=body.mandate_id,
            amount_minor=body.amount_minor,
            currency=body.currency,
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
