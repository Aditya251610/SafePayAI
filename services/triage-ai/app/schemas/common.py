"""Shared response shapes. Wave 4: validation shapes only, no business logic."""

from __future__ import annotations

from pydantic import BaseModel


class ErrorEnvelope(BaseModel):
    """Per docs/service-skeleton-conventions.md section 4 (binding). triage-ai's own
    api.md section 0 documents a differently-shaped transport-error body
    ({"code","message","trace_id"}) — flagged as a conflict in the scaffolding report;
    this flat shape is used for the generic FastAPI exception handlers."""

    error: str
    detail: str
    request_id: str | None = None


class HealthResponse(BaseModel):
    status: str
    service: str


class ReadyResponse(BaseModel):
    status: str
    db: str
