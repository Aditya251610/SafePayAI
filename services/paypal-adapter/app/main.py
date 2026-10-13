"""paypal-adapter FastAPI app. Mounts REST routers, the MCP server, health/readyz, exception
handlers.

orders/captures/refunds/reconcile are real as of Wave 5B (S1-08) + the refund_capture/MCP
wave: create_order, get_order, capture_order, refund_capture, get_refund, reconcile all make
real PayPal sandbox calls via app.ops/app.paypal_client, gated by call_ledger/refund_ledger
idempotency. get_capture, add_tracking, get_tracking, control status/freeze/unfreeze, and the
webhook receiver are also real as of this wave (see app/routers/{captures,tracking,control,
webhooks}.py module docstrings for exactly what was/wasn't verified live). See
docs/service-skeleton-conventions.md and .claude/prd/services/paypal-adapter/{api,spec}.md.
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.mcp import router as mcp_router
from app.routers import (
    captures,
    control,
    health,
    internal,
    orders,
    reconcile,
    refunds,
    tracking,
    webhooks,
)

app = FastAPI(title="paypal-adapter", version="0.1.0")

app.include_router(health.router)
app.include_router(orders.router)
app.include_router(captures.router)
app.include_router(captures.compat_router)
app.include_router(refunds.router)
app.include_router(refunds.compat_router)
app.include_router(tracking.router)
app.include_router(control.router)
app.include_router(reconcile.router)
app.include_router(reconcile.compat_router)
app.include_router(webhooks.router)
app.include_router(internal.router)
app.include_router(mcp_router)


def _request_id(request: Request) -> str:
    return request.headers.get("X-Trace-Id") or str(uuid.uuid4())


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    code = exc.detail if isinstance(exc.detail, str) else "http_error"
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": code.lower() if isinstance(code, str) else "http_error",
            "detail": str(exc.detail),
            "request_id": _request_id(request),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "detail": "request failed schema validation",
            "request_id": _request_id(request),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal",
            "detail": "an unexpected error occurred",
            "request_id": _request_id(request),
        },
    )
