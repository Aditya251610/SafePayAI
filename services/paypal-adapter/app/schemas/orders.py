"""create_order / get_order / capture_order request models, api.md section 5.1-5.3.

ID regex ^[A-Za-z0-9_-]{1,64}$ per api.md section 1. extra=forbid everywhere.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


class CreateOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(pattern=r"^[0-9a-fA-F-]{36}$")
    mandate_id: str = Field(pattern=ID_PATTERN)
    proposal_hash: str
    internal_order_id: str = Field(pattern=ID_PATTERN)
    amount_minor: int = Field(ge=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    return_url: str
    cancel_url: str


class CaptureOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(pattern=r"^[0-9a-fA-F-]{36}$")
    mandate_id: str = Field(pattern=ID_PATTERN)
    proposal_hash: str
    amount_minor: int = Field(ge=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class RefundCaptureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(pattern=r"^[0-9a-fA-F-]{36}$")
    mandate_id: str = Field(pattern=ID_PATTERN)
    proposal_hash: str
    amount_minor: int = Field(ge=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    invoice_id: str | None = Field(default=None, pattern=ID_PATTERN)


class AddTrackingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(pattern=r"^[0-9a-fA-F-]{36}$")
    capture_id: str = Field(pattern=ID_PATTERN)
    tracking_number: str = Field(max_length=64)
    carrier_name_other: str = Field(max_length=64)
    notify_payer: bool = False


class ControlFlagRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
