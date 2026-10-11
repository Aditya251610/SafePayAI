"""FastAPI() app for api-gateway: mounts routers, health/readyz, exception handlers.

Error envelope per docs/service-skeleton-conventions.md section 4. api-gateway's
own spec.md section 11 uses {"error","message","request_id","details"}; the
`message`/`detail` naming difference is reconciled here by emitting both keys so
either convention's readers find what they expect until Wave 5 settles on one.
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.routers import auth, bff, health, jwks, ops, proxy

app = FastAPI(title="api-gateway", version="0.1.0")

app.include_router(health.router)
app.include_router(jwks.router)
app.include_router(auth.router)
app.include_router(ops.router)
app.include_router(bff.router)
app.include_router(proxy.router)


def _request_id(request: Request) -> str:
    return request.headers.get("X-Request-Id", str(uuid.uuid4()))


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    # Routes raise HTTPException(detail=<gateway error code>) (e.g. "UNAUTHENTICATED",
    # "FORBIDDEN", "NOT_FOUND") per spec.md section 11; use that code verbatim as the
    # `error` field so it matches the gateway's own error-code table. Framework-raised
    # HTTPExceptions we didn't construct (e.g. FastAPI's own 404 for an unmatched
    # route) fall back to a generic code derived from the status.
    detail = str(exc.detail)
    code = (
        detail
        if detail.isupper()
        else ("NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR")
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": code,
            "detail": detail,
            "message": detail,
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
            "message": "request validation failed",
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
            "message": "an unexpected error occurred",
            "request_id": _request_id(request),
        },
    )
