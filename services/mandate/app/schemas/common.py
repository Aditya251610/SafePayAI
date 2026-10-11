"""Shared error envelope, mirrors contracts/openapi/mandate.yaml."""

from __future__ import annotations

from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict = {}


class ErrorEnvelope(BaseModel):
    error: str
    detail: str
    request_id: str | None = None
