"""Common response envelope, api.md section 2. One shape for REST and MCP."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    retryable: bool = False
    paypal_name: str | None = None


class Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    status: Literal["OK", "IN_PROGRESS", "REJECTED", "UNKNOWN"]
    paypal_http_status: int | None = None
    data: dict[str, Any] | None = None
    error: ErrorDetail | None = None
    replayed: bool = False
    trace_id: str


def not_implemented_envelope(detail: str, trace_id: str) -> dict[str, Any]:
    return {
        "ok": False,
        "status": "REJECTED",
        "paypal_http_status": None,
        "data": None,
        "error": {
            "code": "not_implemented",
            "message": detail,
            "retryable": False,
            "paypal_name": None,
        },
        "replayed": False,
        "trace_id": trace_id,
    }
