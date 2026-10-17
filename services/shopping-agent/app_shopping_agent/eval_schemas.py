"""Pydantic v2 schemas for the LLM's raw tool output (spec.md section 3) -- NOT the
public API response shapes in app/schemas/propose.py. `extra="forbid"` means a model
that invents a `price`/`total`/`merchant` field fails schema validation outright, which
is itself one of the hard gates the eval harness checks.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, confloat, conint, constr

SkuStr = constr(pattern=r"^[A-Z0-9_-]{3,32}$")


class CartLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: SkuStr  # type: ignore[valid-type]
    quantity: conint(ge=1, le=5)  # type: ignore[valid-type]


class CartProposal(BaseModel):
    """The `propose_cart` tool schema (spec.md section 3)."""

    model_config = ConfigDict(extra="forbid")

    items: list[CartLine] = Field(max_length=5)
    rationale: constr(max_length=300)  # type: ignore[valid-type]
    confidence: confloat(ge=0, le=1)  # type: ignore[valid-type]
    no_match_reason: constr(max_length=200) | None = None  # type: ignore[valid-type]


class IntentFit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal["PASS", "NEEDS_BUYER_CONFIRMATION", "REJECT_WITH_REASON"]
    reason_code: Literal[
        "OK", "CATEGORY_MISMATCH", "QUANTITY_ODD", "RECIPIENT_MISMATCH", "UNCLEAR"
    ]
    reason: constr(max_length=200)  # type: ignore[valid-type]
    confidence: confloat(ge=0, le=1)  # type: ignore[valid-type]


CART_PROPOSAL_JSON_SCHEMA: dict = CartProposal.model_json_schema()
INTENT_FIT_JSON_SCHEMA: dict = IntentFit.model_json_schema()
