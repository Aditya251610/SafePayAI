"""FastAPI() app for catalog: mounts routers, health/readyz, exception handlers.

Error envelope per docs/service-skeleton-conventions.md section 4:
{"error": "<snake_case_code>", "detail": "<human string>", "request_id": "<uuid or null>"}
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.routers import admin, categories, health, items, merchants, prices

app = FastAPI(title="catalog", version="0.1.0")

app.include_router(health.router)
app.include_router(items.router)
app.include_router(merchants.router)
app.include_router(categories.router)
app.include_router(prices.router)
app.include_router(admin.router)


def _request_id(request: Request) -> str:
    return request.headers.get("X-Request-Id", str(uuid.uuid4()))


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
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
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
