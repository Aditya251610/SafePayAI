"""Shared response shapes. Wave 4: validation shapes only, no business logic."""

from __future__ import annotations

from pydantic import BaseModel


class ErrorEnvelope(BaseModel):
    """Per docs/service-skeleton-conventions.md section 4 (binding across all services)."""

    error: str
    detail: str
    request_id: str | None = None


class HealthResponse(BaseModel):
    status: str
    service: str


class ReadyResponse(BaseModel):
    status: str
    db: str
