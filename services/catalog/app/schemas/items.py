"""Pydantic schemas for items/merchants/categories/version, mirrors catalog.yaml."""

from __future__ import annotations

from pydantic import BaseModel


class Item(BaseModel):
    sku: str
    merchant_id: str
    category_id: str
    title: str
    description: str
    unit_price_minor: int
    currency: str
    active: bool
    text_trust: str = "untrusted"
    label: str = "SIMULATED"


class ItemDetailResponse(Item):
    catalog_version: int


class ItemsResponse(BaseModel):
    catalog_version: int
    items: list[Item]
    limit: int
    offset: int
    has_more: bool


class Merchant(BaseModel):
    merchant_id: str
    display_name: str
    settlement_alias: str
    currency: str


class MerchantsResponse(BaseModel):
    merchants: list[Merchant]


class Category(BaseModel):
    category_id: str
    display_name: str


class CategoriesResponse(BaseModel):
    categories: list[Category]


class CatalogVersionResponse(BaseModel):
    catalog_version: int
    seed_hash: str
    item_count: int
    merchant_count: int


class RefundPolicySeedResponse(BaseModel):
    merchant_id: str
    refund_cap_minor: int
    currency: str
    excluded_category_ids: list[str]
    velocity_max_refunds: int
    velocity_window_days: int
    authoritative: bool = False
    note: str
