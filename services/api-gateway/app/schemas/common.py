"""Shared error envelope, mirrors contracts/openapi/api-gateway.yaml and spec.md section 11."""

from __future__ import annotations

from pydantic import BaseModel


class ErrorEnvelope(BaseModel):
    error: str
    message: str
    request_id: str | None = None
    details: dict | None = None
