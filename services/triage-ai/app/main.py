"""triage-ai service entrypoint. Mounts routers, health/readyz, exception handlers.

Wave 4 scaffold: see docs/service-skeleton-conventions.md. No business logic beyond the
health routes. No outbound HTTP calls to other services anywhere in this app (ADR-010).
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.routers import health, triage

app = FastAPI(title="triage-ai", version="0.1.0")

app.include_router(health.router)
app.include_router(triage.router)


def _envelope(error: str, detail: str, request_id: str | None) -> dict:
    return {"error": error, "detail": detail, "request_id": request_id}


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    request_id = request.headers.get("X-Request-Id")
    code = "not_implemented" if exc.status_code == 501 else "http_error"
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(code, str(exc.detail), request_id),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    request_id = request.headers.get("X-Request-Id")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_envelope("invalid_request", str(exc.errors()), request_id),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_envelope("internal", "an unexpected error occurred", request_id),
    )
