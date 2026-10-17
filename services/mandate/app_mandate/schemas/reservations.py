"""Cart/evaluate/reservation schemas, mirrors mandate/api.md sections 9-11."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CartLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str
    qty: int = Field(ge=1)
    unit_minor: int = Field(ge=0)
    line_minor: int = Field(ge=0)
    merchant_id: str
    sku_known: bool
    stated_unit_minor: int | None = Field(default=None, ge=0)


class Cart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: str
    lines: list[CartLine]
    total_minor: int = Field(ge=0)


class EvaluateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cart: Cart
    committed_minor: int | None = None


class ReservationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str
    amount_minor: int = Field(gt=0)
    currency: str
    proposal_hash: str
    cart: Cart


class AuthorizeCaptureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str
    amount_minor: int = Field(gt=0)


class MarkUnknownRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason_code: str


class CommitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capture_id: str
    captured_amount_minor: int = Field(gt=0)
    currency: str
    captured_at: str


class ReleaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason_code: str
    capture_outcome: str | None = None
