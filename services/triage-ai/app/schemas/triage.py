"""Request/response schemas mirroring contracts/openapi/triage-ai.yaml, derived from
triage-ai/api.md sections 1-3 and spec.md section 4. Wave 4: schema shapes only; routes
still return 501. extra="forbid" per spec.md section 4 (strict, unknown fields -> 422)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Category = Literal["LATE", "LOST", "DAMAGED", "WRONG_ITEM", "NOT_AS_DESCRIBED", "OTHER"]
Route = Literal["PROCEED", "HUMAN_REVIEW"]
Source = Literal["live", "cached", "template", "rules"]
ShipStatus = Literal["LABEL_CREATED", "SHIPPED", "IN_TRANSIT", "DELAYED", "DELIVERED", "LOST_FLAGGED", "UNKNOWN"]


class TimelineEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    ts: datetime
    status: ShipStatus
    note: str | None = Field(default=None, max_length=300)


class OrderFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_ref: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    order_date: date
    promised_by: date | None = None
    demo_now: datetime
    state: str = Field(max_length=40)
    item_titles: list[str] = Field(default_factory=list, max_length=5)
    amount_minor: int | None = Field(default=None, ge=0)  # /brief only; ignored elsewhere
    currency: Literal["USD"] | None = None


class Provenance(BaseModel):
    source: Source
    model: str | None = None
    prompt_version: str
    cached_at: datetime | None = None
    latency_ms: int


class InconsistencyFlag(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    severity: Literal["INFO", "WARN"]
    origin: Literal["rule", "model"]
    event_ids: list[str] = Field(default_factory=list, max_length=5)
    explanation: str = Field(max_length=160)


class ClassifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    trace_id: str
    origin: Literal["buyer_report", "detector"]
    buyer_text: str | None = Field(default=None, max_length=4000)
    timeline: list[TimelineEvent] = Field(default_factory=list, max_length=30)
    order: OrderFacts


class ClassifyResponse(BaseModel):
    triage_id: UUID
    category: Category
    confidence: float = Field(ge=0, le=1)
    route: Route
    reasons: list[str] = Field(default_factory=list)
    timeline_flags: list[InconsistencyFlag] = Field(default_factory=list)
    provenance: Provenance


class DraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    trace_id: str
    audience: Literal["buyer", "merchant"]
    category: Category
    outcome: Literal["REFUND_OFFER_INSIDE_TERMS", "APPROVAL_REQUESTED", "UNDER_REVIEW", "INFO_REQUEST"]
    order_ref: str


class DraftResponse(BaseModel):
    triage_id: UUID
    subject: str = Field(max_length=80)
    body: str = Field(max_length=600)
    placeholders_used: list[Literal["{amount}", "{order_ref}", "{date}", "{buyer_name}"]] = Field(default_factory=list)
    gate: Literal["PASSED", "REJECTED_USED_TEMPLATE"]
    gate_hits: list[str] = Field(default_factory=list)
    provenance: Provenance


class BriefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    trace_id: str
    buyer_text: str | None = Field(default=None, max_length=4000)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    order: OrderFacts
    triage: ClassifyResponse | None = None
    policy_decision: str | None = Field(default=None, max_length=40)


class KeyFact(BaseModel):
    field: str
    value: str
    source_field: str


class BriefResponse(BaseModel):
    triage_id: UUID
    summary: str = Field(max_length=500)
    key_facts: list[KeyFact] = Field(default_factory=list)
    inconsistency_flags: list[InconsistencyFlag] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list, max_length=4)
    read_only: Literal[True] = True
    provenance: Provenance


class TransportErrorBody(BaseModel):
    """Transport-error shape per api.md section 0 (distinct from fail-closed 200 bodies)."""

    code: str
    message: str
    trace_id: str | None = None
