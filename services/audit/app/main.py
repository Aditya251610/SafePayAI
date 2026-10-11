"""FastAPI app factory for the audit service.

Mounts routers, wires the request-id middleware, and normalizes every non-2xx response
into the error envelope from service-skeleton-conventions.md sec 4:
`{"error": "<snake_case_code>", "detail": "<human string>", "request_id": "<uuid or null>"}`.
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.routers import entries, events, export, head, health, verify
from app.settings import get_settings

_STATUS_CODES = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_401_UNAUTHORIZED: "unauthenticated",
    status.HTTP_403_FORBIDDEN: "forbidden",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_422_UNPROCESSABLE_ENTITY: "validation_error",
    status.HTTP_429_TOO_MANY_REQUESTS: "rate_limited",
    status.HTTP_501_NOT_IMPLEMENTED: "not_implemented",
    status.HTTP_503_SERVICE_UNAVAILABLE: "db_unavailable",
}


def _default_code_for_status(status_code: int) -> str:
    return _STATUS_CODES.get(status_code, "internal_error")


def create_app() -> FastAPI:
    settings = get_settings()

    # Startup guard (spec.md sec 8): migrate_database_url is CI/migration-only and must
    # never be configured in the same env as the pooled runtime database_url.
    if settings.migrate_database_url and settings.env != "ci":
        raise RuntimeError(
            "PS_AUDIT_MIGRATE_DATABASE_URL must not be set at runtime (spec.md sec 8); "
            "it is a CI/migration-only, direct-endpoint, audit_owner credential."
        )

    app = FastAPI(title="SafePayAI Audit Service", version="0.1.0")

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        detail = exc.detail
        if isinstance(detail, dict) and "error" in detail:
            body = {
                "error": detail["error"],
                "detail": detail.get("detail") or detail.get("message") or "",
                "request_id": detail.get("request_id", request_id),
            }
        else:
            body = {
                "error": _default_code_for_status(exc.status_code),
                "detail": str(detail),
                "request_id": request_id,
            }
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": "validation_error", "detail": exc.errors(), "request_id": request_id},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "internal_error",
                "detail": "An unexpected error occurred.",
                "request_id": request_id,
            },
        )

    app.include_router(health.router)
    app.include_router(events.router)
    app.include_router(entries.router)
    app.include_router(verify.router)
    app.include_router(head.router)
    app.include_router(export.router)

    return app


app = create_app()
