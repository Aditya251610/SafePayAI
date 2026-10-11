"""Request/response models mirroring contracts/openapi/shopping-agent.yaml and
.claude/prd/services/shopping-agent/api.md sections 4-6. Wave 4: validation only, no
business logic. extra="forbid" everywhere per api.md section 1 (no price/total/merchant
field ever accepted).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FormIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    max_budget_minor: int = Field(ge=0)
    quantity: int = Field(ge=1, le=5)
    merchant_id: str | None = None
    keywords: str | None = None


class ProposeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mandate_id: str
    mode: Literal["intent", "form"]
    intent_text: str | None = Field(default=None, max_length=500)
    catalog_snapshot_id: str | None = None
    form: FormIntent | None = None


class CartLineOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str
    quantity: int
    display_title: str | None = None


class ProposeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    status: Literal["OK", "NO_MATCH", "NO_PROPOSAL", "AI_PAUSED"]
    source: Literal["live", "cached", "form"]
    lines: list[CartLineOut] = Field(default_factory=list)
    rationale: str | None = None
    confidence: float | None = None
    no_match_reason: str | None = None
    model: str | None = None
    latency_ms: int | None = None
    badge: str | None = None
    recorded_model: str | None = None
    trace_id: str


class IntentFitCartLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str
    quantity: int
    title: str
    category: str


class IntentFitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mandate_id: str
    intent_text: str
    cart_lines: list[IntentFitCartLine]


class IntentFitResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal["PASS", "NEEDS_BUYER_CONFIRMATION", "REJECT_WITH_REASON"]
    reason_code: Literal["OK", "CATEGORY_MISMATCH", "QUANTITY_ODD", "RECIPIENT_MISMATCH", "UNCLEAR"]
    reason: str = Field(max_length=200)
    confidence: float
    advisory: bool = True
    degraded: bool = False
    source: Literal["live", "cached", "form"]
    trace_id: str


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: str
    detail: str
    request_id: str | None = None
