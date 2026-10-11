"""Cart/order request/response models mirroring api.md sections 3-4. extra=forbid: client-
sent amount/currency/merchant/capture_id are rejected, not silently ignored (api.md section 1).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CartLineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str
    qty: int = Field(ge=1)


class CreateCartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mandate_id: str
    lines: list[CartLineIn]
    proposal_id: str | None = None
    stated_unit_prices_minor: dict[str, int] | None = None


class CartCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    result: Literal["PASS", "BLOCK", "TIGHTEN", "SKIPPED"]
    reason_code: str | None = None
    source: str
    advisory: bool | None = None


class CartLineOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str
    qty: int
    unit_minor: int
    line_minor: int
    merchant_id: str


class IntentFitSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal["PASS", "NEEDS_BUYER_CONFIRMATION", "REJECT_WITH_REASON"]
    reason_code: str
    advisory: bool = True


class CreateCartResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cart_id: str
    status: Literal["CHECKED", "NEEDS_CONFIRMATION", "BLOCKED"]
    currency: str
    lines: list[CartLineOut]
    total_minor: int
    remaining_cap_minor_after: int
    proposal_hash: str
    checks: list[CartCheck]
    intent_fit: IntentFitSummary | None = None
    expires_at: str


class ConfirmCartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_hash: str
    confirm_intent_fit: bool = False


class ConfirmCartResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str
    status: str
    approve_url: str
    total_minor: int
    currency: str
    expires_at: str


class OrderReturnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str
    token: str
    payer_id: str


class OrderReturnResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str
    status: Literal[
        "CAPTURED", "CAPTURE_PENDING", "CAPTURE_UNKNOWN", "CANCELLED_REVOKED", "CAPTURE_FAILED"
    ]
    receipt_url: str
    message_code: Literal[
        "CAPTURED", "PENDING_PROTECTION_NOT_STARTED", "MANDATE_REVOKED", "TRY_AGAIN"
    ]


class OrderCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str


class CaptureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: str
    detail: str
    request_id: str | None = None
