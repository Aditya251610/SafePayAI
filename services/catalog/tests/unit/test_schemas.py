"""U8: strict body validation (extra=forbid) and basic shape checks, no DB needed."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app_catalog.errors import CatalogError
from app_catalog.schemas.prices import PriceResolveLine, PriceResolveRequest


def test_price_resolve_request_rejects_unknown_top_level_field():
    with pytest.raises(ValidationError):
        PriceResolveRequest(lines=[{"sku": "TH-001", "qty": 1}], total=100)  # type: ignore[call-arg]


def test_price_resolve_line_rejects_unknown_field():
    with pytest.raises(ValidationError):
        PriceResolveLine(sku="TH-001", qty=1, price=100)  # type: ignore[call-arg]


def test_price_resolve_line_accepts_documented_agent_stated_price():
    line = PriceResolveLine(sku="TH-001", qty=1, agent_stated_price_minor=1800)
    assert line.agent_stated_price_minor == 1800


def test_price_resolve_line_qty_must_be_int_not_float():
    with pytest.raises(ValidationError):
        PriceResolveLine(sku="TH-001", qty=1.5)  # type: ignore[arg-type]


def test_price_resolve_request_currency_and_catalog_version_optional():
    req = PriceResolveRequest(lines=[{"sku": "TH-001", "qty": 1}])
    assert req.currency is None
    assert req.catalog_version is None


def test_catalog_error_carries_code_message_details():
    err = CatalogError(422, "UNKNOWN_SKU", "nope", {"skus": ["X"]})
    assert err.status_code == 422
    assert err.code == "UNKNOWN_SKU"
    assert err.details == {"skus": ["X"]}
