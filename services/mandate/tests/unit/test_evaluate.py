"""MD-T: one failing-fixture test per hard-block code in spec.md section 6.2 (closed
list of 11 codes including MANDATE_INTEGRITY_FAILED), plus the advisory/decision
independence property test."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.mandate_logic import evaluate_cart

NOW = datetime(2026, 10, 20, 12, 0, 0, tzinfo=UTC)
FAR_FUTURE = NOW + timedelta(days=10)
MERCHANTS = [{"merchant_id": "shop-a", "display_name": "Shop A"}]


def _base_kwargs(**overrides):
    kwargs = {
        "integrity_ok": True,
        "status": "active",
        "merchant_allowlist": MERCHANTS,
        "max_qty_per_line": 5,
        "currency": "USD",
        "remaining_minor": 10_000,
        "cart": {
            "currency": "USD",
            "lines": [
                {
                    "sku": "sku-1",
                    "qty": 1,
                    "unit_minor": 2500,
                    "line_minor": 2500,
                    "merchant_id": "shop-a",
                    "sku_known": True,
                    "stated_unit_minor": 2500,
                }
            ],
            "total_minor": 2500,
        },
        "expires_at": FAR_FUTURE,
        "now": NOW,
        "near_cap_percent": 90,
        "expires_soon_seconds": 3600,
    }
    kwargs.update(overrides)
    return kwargs


def test_allow_when_no_hard_blocks():
    result = evaluate_cart(**_base_kwargs())
    assert result.decision == "ALLOW"
    assert result.hard_blocks == []


def test_mandate_integrity_failed_short_circuits():
    kwargs = _base_kwargs(integrity_ok=False, status="revoked")  # even with other blocks present
    result = evaluate_cart(**kwargs)
    assert result.decision == "BLOCK"
    assert result.hard_blocks == [{"code": "MANDATE_INTEGRITY_FAILED", "details": {}}]


def test_mandate_revoked():
    result = evaluate_cart(**_base_kwargs(status="revoked"))
    assert result.decision == "BLOCK"
    assert any(b["code"] == "MANDATE_REVOKED" for b in result.hard_blocks)


def test_mandate_expired():
    result = evaluate_cart(**_base_kwargs(status="expired"))
    assert any(b["code"] == "MANDATE_EXPIRED" for b in result.hard_blocks)


def test_mandate_exhausted():
    result = evaluate_cart(**_base_kwargs(status="exhausted"))
    assert any(b["code"] == "MANDATE_EXHAUSTED" for b in result.hard_blocks)


def test_merchant_not_allowed():
    cart = _base_kwargs()["cart"]
    cart["lines"][0]["merchant_id"] = "shop-z"
    result = evaluate_cart(**_base_kwargs(cart=cart))
    block = next(b for b in result.hard_blocks if b["code"] == "MERCHANT_NOT_ALLOWED")
    assert block["details"]["merchant_ids"] == ["shop-z"]


def test_over_cap():
    result = evaluate_cart(**_base_kwargs(remaining_minor=100))
    block = next(b for b in result.hard_blocks if b["code"] == "OVER_CAP")
    assert block["details"]["remaining_minor"] == 100


def test_unknown_sku():
    cart = _base_kwargs()["cart"]
    cart["lines"][0]["sku_known"] = False
    result = evaluate_cart(**_base_kwargs(cart=cart))
    assert any(b["code"] == "UNKNOWN_SKU" for b in result.hard_blocks)


def test_qty_cap():
    cart = _base_kwargs()["cart"]
    cart["lines"][0]["qty"] = 10
    cart["lines"][0]["line_minor"] = 25000
    cart["total_minor"] = 25000
    result = evaluate_cart(**_base_kwargs(cart=cart, max_qty_per_line=5, remaining_minor=100_000))
    assert any(b["code"] == "QTY_CAP" for b in result.hard_blocks)


def test_currency_mismatch():
    cart = _base_kwargs()["cart"]
    cart["currency"] = "EUR"
    result = evaluate_cart(**_base_kwargs(cart=cart))
    assert any(b["code"] == "CURRENCY_MISMATCH" for b in result.hard_blocks)


def test_price_mismatch():
    cart = _base_kwargs()["cart"]
    cart["lines"][0]["stated_unit_minor"] = 1
    result = evaluate_cart(**_base_kwargs(cart=cart))
    block = next(b for b in result.hard_blocks if b["code"] == "PRICE_MISMATCH")
    assert block["details"]["skus"] == ["sku-1"]


def test_cart_arithmetic_mismatch():
    cart = _base_kwargs()["cart"]
    cart["total_minor"] = 999999
    result = evaluate_cart(**_base_kwargs(cart=cart))
    assert any(b["code"] == "CART_ARITHMETIC_MISMATCH" for b in result.hard_blocks)


def test_hard_block_order_is_fixed():
    # Trigger several blocks at once; order must follow the spec table.
    cart = {
        "currency": "EUR",
        "lines": [
            {
                "sku": "sku-1",
                "qty": 1,
                "unit_minor": 2500,
                "line_minor": 2500,
                "merchant_id": "shop-z",
                "sku_known": False,
                "stated_unit_minor": 1,
            }
        ],
        "total_minor": 2500,
    }
    result = evaluate_cart(**_base_kwargs(status="exhausted", remaining_minor=0, cart=cart))
    codes = [b["code"] for b in result.hard_blocks]
    expected_order = [
        "MANDATE_EXHAUSTED",
        "MERCHANT_NOT_ALLOWED",
        "OVER_CAP",
        "UNKNOWN_SKU",
        "CURRENCY_MISMATCH",
        "PRICE_MISMATCH",
    ]
    assert codes == expected_order


def test_advisory_flags_never_change_decision():
    kwargs = _base_kwargs(remaining_minor=2500)  # triggers NEAR_CAP but still ALLOW
    result = evaluate_cart(**kwargs)
    assert result.decision == "ALLOW"
    assert any(f["code"] == "NEAR_CAP" for f in result.advisory_flags)
