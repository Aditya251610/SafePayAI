"""Internal event inbox / reconcile models, api.md section 10."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class InboundEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    type: str
    version: int
    occurred_at: str
    producer: str
    aggregate_id: str
    trace_id: str | None = None
    payload: dict[str, Any]
