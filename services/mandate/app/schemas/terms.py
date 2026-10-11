"""Signed mandate terms schemas, mirrors mandate/spec.md section 2.1 and api.md section 4-5.

extra="forbid" everywhere (mandate bodies never accept extra fields; client-sent
buyer_id/status/spent_minor/mandate_hash/hmac/mandate_id/created_at -> 422
FIELD_NOT_ALLOWED per api.md section 1). Money = integer minor units only.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MerchantAllowlistEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    merchant_id: str
    display_name: str


class ProtectionTerms(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kinds_covered: list[str]
    max_refund_minor: int = Field(gt=0)
    deliver_by_days: int = Field(gt=0)


class MandateTermsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: str
    max_total_minor: int = Field(gt=0)
    max_qty_per_line: int | None = Field(default=None, ge=1)
    merchant_allowlist: list[MerchantAllowlistEntry]
    intent_text: str
    expires_at: str
    protection: ProtectionTerms
    policy_version: str | None = None
    revoke_effect: str | None = None


class MandatePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    terms: MandateTermsInput


class MandatePreviewResponse(BaseModel):
    normalized_terms: dict
    screen_text: str
    screen_text_hash: str
    render_version: str
    policy_version: str
    nonce: str
    nonce_expires_at: str


class MandateSignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    terms: MandateTermsInput
    screen_text_hash: str
    nonce: str


class RevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason_code: str
