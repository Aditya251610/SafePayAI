"""shopping-agent FastAPI app. Mounts routers, health/readyz, exception handlers.

Wave 4 scaffold only: every business route is a 501 stub; /healthz and /readyz are real.
See docs/service-skeleton-conventions.md and .claude/prd/services/shopping-agent/api.md.
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app_shopping_agent.routers import health, intent_fit, internal, propose
from app_shopping_agent.settings import get_settings

get_settings()  # fail fast on a placeholder secret before serving any request

app = FastAPI(title="shopping-agent", version="0.1.0")

app.include_router(health.router)
app.include_router(propose.router)
app.include_router(intent_fit.router)
app.include_router(internal.router)


def _request_id(request: Request) -> str:
    return request.headers.get("X-Request-Id") or str(uuid.uuid4())


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
