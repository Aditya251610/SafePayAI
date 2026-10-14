"""FastAPI() app for mandate: mounts routers, health/readyz, exception handlers.

Error envelope per docs/service-skeleton-conventions.md section 4. mandate's own
api.md section 3 uses a richer {"error":{"code",...}} shape; the top-level
{"error","detail","request_id"} shape here satisfies the binding conventions doc,
and `detail` carries the mandate-specific stable code until Wave 5 widens the body.
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.errors import MandateError
from app.routers import grants, health, internal, mandates, reservations
from app.settings import get_bare_secrets, get_settings

get_settings()
get_bare_secrets()  # fail fast on a placeholder secret before serving any request

app = FastAPI(title="mandate", version="0.1.0")

app.include_router(health.router)
app.include_router(mandates.router)
app.include_router(reservations.router)
app.include_router(grants.router)
app.include_router(internal.router)


def _request_id(request: Request) -> str:
    return request.headers.get("X-Request-Id", str(uuid.uuid4()))


@app.exception_handler(MandateError)
async def mandate_error_handler(request: Request, exc: MandateError) -> JSONResponse:
    """mandate's own richer error envelope per api.md section 3:
    {"error":{"code","message","details"},"request_id"}."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {"code": exc.code, "message": exc.message, "details": exc.details},
            "request_id": _request_id(request),
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "http_error" if exc.status_code != 404 else "not_found",
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
            "detail": "request validation failed",
            "request_id": _request_id(request),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "detail": "an unexpected error occurred",
            "request_id": _request_id(request),
        },
    )
