"""paypal-adapter FastAPI app. Mounts REST routers, the MCP stub, health/readyz, exception
handlers.

Wave 4 scaffold only: every money/read/write business route is a 501 stub (envelope shape
per api.md section 2); /healthz, /health, and /readyz are real. No real PayPal calls (never
import a PayPal SDK or call api-m.sandbox.paypal.com from this codebase in Wave 4). See
docs/service-skeleton-conventions.md and .claude/prd/services/paypal-adapter/{api,spec}.md.
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.mcp import router as mcp_router
from app.routers import captures, control, health, orders, reconcile, refunds, tracking, webhooks

app = FastAPI(title="paypal-adapter", version="0.1.0")

app.include_router(health.router)
app.include_router(orders.router)
app.include_router(captures.router)
app.include_router(refunds.router)
app.include_router(tracking.router)
app.include_router(control.router)
app.include_router(reconcile.router)
app.include_router(webhooks.router)
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
