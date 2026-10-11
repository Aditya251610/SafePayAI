"""checkout FastAPI app. Mounts routers, health/readyz, exception handlers.

Wave 4 scaffold only: every business route is a 501 stub; /healthz and /readyz are real.
See docs/service-skeleton-conventions.md and .claude/prd/services/checkout/api.md.
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.errors import CheckoutError
from app.routers import carts, health, internal, orders

app = FastAPI(title="checkout", version="0.1.0")

app.include_router(health.router)
app.include_router(carts.router)
app.include_router(orders.router)
app.include_router(internal.router)


def _request_id(request: Request) -> str:
    return request.headers.get("X-Request-Id") or str(uuid.uuid4())


@app.exception_handler(CheckoutError)
async def checkout_error_handler(request: Request, exc: CheckoutError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.code,
            "detail": exc.message,
            "request_id": _request_id(request),
            "details": exc.details,
        },
    )


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
