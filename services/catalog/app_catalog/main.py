"""FastAPI() app for catalog: mounts routers, health/readyz, exception handlers.

Error envelope per docs/service-skeleton-conventions.md section 4, extended per
app/errors.py's documented rationale: {"error": "<code>", "detail": "<human string>",
"request_id": "<uuid or null>", "details": {}}.

Data-label/request-id headers per catalog/api.md: every response carries
`X-Data-Label: simulated-seed` and `X-Request-Id` (echoed from the caller if present,
else generated).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app_catalog.errors import CatalogError
from app_catalog.routers import admin, categories, health, items, merchants, prices

app = FastAPI(title="catalog", version="0.1.0")

app.include_router(health.router)
app.include_router(items.router)
app.include_router(merchants.router)
app.include_router(categories.router)
app.include_router(prices.router)
app.include_router(admin.router)


def _request_id(request: Request) -> str:
    return request.headers.get("X-Request-Id", str(uuid.uuid4()))


@app.middleware("http")
async def add_data_label_headers(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request_id = _request_id(request)
    response = await call_next(request)
    response.headers["X-Data-Label"] = "simulated-seed"
    response.headers.setdefault("X-Request-Id", request_id)
    return response


@app.exception_handler(CatalogError)
async def catalog_error_handler(request: Request, exc: CatalogError) -> JSONResponse:
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
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "http_error" if exc.status_code != 404 else "not_found",
            "detail": str(exc.detail),
            "request_id": _request_id(request),
            "details": {},
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": "VALIDATION_ERROR",
            "detail": "request validation failed",
            "request_id": _request_id(request),
            "details": {"errors": jsonable_encoder(exc.errors())},
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
            "details": {},
        },
    )
