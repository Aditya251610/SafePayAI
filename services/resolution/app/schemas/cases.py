"""Request/response schemas mirroring contracts/openapi/resolution.yaml, derived from
resolution/api.md sections 3.1-3.11. Wave 4: schema shapes only; routes still return 501."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Kind = Literal["LATE", "LOST", "DAMAGED", "WRONG_ITEM", "NOT_AS_DESCRIBED", "OTHER"]
CaseState = Literal[
    "PROTECTED",
    "MONITORING",
    "PROBLEM_DETECTED",
    "TRIAGED",
    "OFFERED",
    "HUMAN_REVIEW",
    "APPROVED",
    "REFUNDING",
    "RESOLVED_REFUNDED",
    "RESOLVED_RESHIP",
    "DECLINED",
    "CLOSED",
]


class Reason(BaseModel):
    code: str
    text: str | None = None


class ReportCaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: str
    text: str = Field(max_length=4000)


class OfferView(BaseModel):
    offer_id: str
    action: Literal["REFUND", "RESHIP"]
    amount_minor: int
    currency: str
    tier: Literal["AUTO", "CONFIRM", "APPROVE", "REVIEW"]
    status: str
    proposal_hash: str
    expires_at: str


class ReportCaseResponse(BaseModel):
    case_id: str
    state: CaseState
    kind: Kind
    origin: Literal["BUYER_REPORT"]
    reasons: list[Reason] = Field(default_factory=list)
    offer: OfferView | None = None
    protection: dict = Field(default_factory=dict)


class CaseTimelineEntry(BaseModel):
    from_state: str | None = Field(default=None, alias="from")
    to: str
    actor: str
    reason: str | None = None
    at: str

    model_config = ConfigDict(populate_by_name=True)


class DecisionView(BaseModel):
    klass: Literal["INSIDE_TERMS", "OUTSIDE_TERMS", "HUMAN_REVIEW", "MERCHANT_OVERRIDE"] = Field(alias="class")
    policy_version: str
    reasons: list[Reason] = Field(default_factory=list)
    illustrative: bool = True

    model_config = ConfigDict(populate_by_name=True)


class RefundView(BaseModel):
    status: Literal["NONE", "REQUESTED", "SENT", "COMPLETED", "FAILED", "UNKNOWN", "NOT_SENT"]
    paypal_refund_id: str | None = None


class CaseDetailResponse(BaseModel):
    case_id: str
    order_id: str
    state: CaseState
    version: int
    kind: Kind
    origin: Literal["DETECTOR", "BUYER_REPORT"]
    opened_at: str
    window_hold: bool
    timeline: list[CaseTimelineEntry] = Field(default_factory=list)
    decision: DecisionView | None = None
    offer: OfferView | None = None
    refund: RefundView | None = None
    queued_reason: str | None = None


class ReviewQueueItem(BaseModel):
    case_id: str
    kind: Kind
    reason_codes: list[str] = Field(default_factory=list)
    entered_at: str
    age_s: int
    sla_target_s: int | None = None
    sla_state: Literal["NO_TARGET", "WITHIN", "OVER"]
    brief: str


class ReviewQueueResponse(BaseModel):
    items: list[ReviewQueueItem] = Field(default_factory=list)


class ReviewDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["PROPOSE_REFUND", "PROPOSE_RESHIP", "DECLINE", "CLOSE"]
    reviewer_name: str
    reason: str | None = None


class ReviewDecisionResponse(BaseModel):
    case_id: str
    state: CaseState
    offer_id: str | None = None


class OfferAcceptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposal_hash: str


class OfferAcceptResponse(BaseModel):
    case_id: str
    state: CaseState
    execution: Literal["DONE", "IN_PROGRESS", "QUEUED_FROZEN", "NOT_STARTED"]
    refund: RefundView


class OfferDeclineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason_code: Literal["NOT_WANTED", "WANT_HUMAN", "OTHER"]


class OfferDeclineResponse(BaseModel):
    state: Literal["DECLINED"]


class ApprovalPreviewResponse(BaseModel):
    case_id: str
    action: Literal["REFUND", "RESHIP"]
    amount_minor: int
    currency: str
    summary: str
    expires_at: str
    proposal_hash: str


class ApprovalConsentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposal_hash: str
    csrf_nonce: str


class ApprovalConsentResponse(BaseModel):
    case_id: str
    state: CaseState
    execution: Literal["DONE", "IN_PROGRESS", "QUEUED_FROZEN"]


class MerchantActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["OVERRIDE_OFFER", "CONFIRM_RESHIP"]


class MerchantActionResponse(BaseModel):
    case_id: str
    state: CaseState
    offer_id: str | None = None
    supersedes: str | None = None


class AppealRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str | None = None


class AppealResponse(BaseModel):
    state: Literal["HUMAN_REVIEW"]


class ReconcileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = 25


class ReconcileResponse(BaseModel):
    examined: int = 0
    finalized_completed: int = 0
    finalized_failed: int = 0
    still_unknown: int = 0
    needs_review: int = 0
    frozen_skipped_replays: int = 0


class RefundsFrozenState(BaseModel):
    refunds_frozen: bool
    reason: str | None = None
    set_by: str | None = None
    set_at: str | None = None
    epoch: int = 0
    adapter_mirror: Literal["ACKED", "PENDING"] = "PENDING"
    readable: bool = True


class RefundsFrozenPutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    refunds_frozen: bool
    reason: str = Field(min_length=1)


class NotificationView(BaseModel):
    id: str
    case_id: str
    type: str
    created_at: str
    body: str


class NotificationsResponse(BaseModel):
    items: list[NotificationView] = Field(default_factory=list)


class InternalEventEnvelope(BaseModel):
    event_id: UUID
    type: str
    version: int
    aggregate_id: str
    payload: dict
    trace_id: str | None = None
