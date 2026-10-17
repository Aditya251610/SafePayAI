"""Request/response models for POST /internal/events(/batch) -- api.md sec 1.

Payload per-event-type schemas (contracts/events/audit-<TYPE>.v1.json, spec.md sec 6) are
Wave 5 work; here `payload` is validated only as "a JSON object", matching this wave's
"contracts + skeleton, not business logic" scope.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ActorRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    id: str
    auth_method: str
    session_id_hash: str | None = None


class SubjectRefs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    buyer_id: str | None = None
    mandate_id: str | None = None
    order_id: str | None = None
    case_id: str | None = None


class EventEnvelope(BaseModel):
    """Mirrors api.md sec 1 request body for POST /internal/events."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    type: str
    version: int
    occurred_at: datetime
    producer: str
    aggregate_id: str | None = None
    trace_id: str
    request_id: str
    actor: ActorRef
    refs: SubjectRefs = Field(default_factory=SubjectRefs)
    payload: dict[str, Any]


class EventBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[EventEnvelope]


class AppendResult(BaseModel):
    seq: int
    row_hash: str
    duplicate: bool


class BatchItemResult(BaseModel):
    event_id: str
    status: Literal["APPENDED", "DUPLICATE", "REJECTED"]
    seq: int | None = None
    error: str | None = None


class BatchResponse(BaseModel):
    results: list[BatchItemResult]
