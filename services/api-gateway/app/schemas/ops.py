"""Ops endpoint schemas, mirrors api-gateway/api.md section 3."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class OpsStatusResponse(BaseModel):
    demo_mode: bool
    money_routes_enabled: bool
    refunds_frozen: str
    build_id: str


class FreezeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frozen: bool
    reason: str | None = None


class FreezeResponse(BaseModel):
    refunds_frozen: str
    changed_at: str


class TickResponse(BaseModel):
    detector: str
    reconcile: str
