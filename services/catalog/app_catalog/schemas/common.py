"""Shared response/error envelope schemas, mirrors contracts/openapi/catalog.yaml."""

from __future__ import annotations

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict = {}
    request_id: str | None = None


class ErrorEnvelope(BaseModel):
    error: str
    detail: str
    request_id: str | None = None


class NotImplementedBody(BaseModel):
    error: str = "not_implemented"
    detail: str
