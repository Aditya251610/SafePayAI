"""Pydantic schemas for POST /prices/resolve, mirrors catalog.yaml.

Money fields use integer minor units with a currency sibling (never float),
per docs/service-skeleton-conventions.md section 8 / data-architecture.md section 5.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PriceResolveLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str
    qty: int = Field(ge=1)
    agent_stated_price_minor: int | None = None


class PriceResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lines: list[PriceResolveLine]
    currency: str | None = None
    catalog_version: int | None = None


class PricedLine(BaseModel):
    sku: str
    merchant_id: str
    category_id: str
    qty: int
    unit_price_minor: int
    line_total_minor: int
    settlement_alias: str
    price_mismatch: bool
    latest_unit_price_minor: int | None = None


class PriceResolveResponse(BaseModel):
    catalog_version: int
    currency: str
    lines: list[PricedLine]
    merchant_ids: list[str]
    total_minor: int
    price_mismatch_any: bool
