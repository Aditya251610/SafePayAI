"""Unit tests for the receipt builder (sprint-plan S2-02) -- no DB, no HTTP. The
forbidden-claim test is the one sprint-plan S2-02 explicitly calls for: a snapshot
check of receipt text against CLAUDE.md's honesty-rule forbidden phrases.
"""

from __future__ import annotations

from app_checkout.routers.orders import _amount_major, _build_receipt_json

# CLAUDE.md "Honesty rules": never claim these, regardless of case.
FORBIDDEN_CLAIM_PHRASES = (
    "paypal-backed",
    "paypal backed",
    "paypal-verified",
    "paypal verified",
    "legally binding",
    "non-repudiable",
    "nonrepudiable",
    "compliant",
    "fraud-proof",
    "fraud proof",
    "injection-proof",
    "injection proof",
)

REQUIRED_PHRASE = "merchant-funded via paypal refund"


def _order_row() -> dict:
    return {
        "order_id": "11111111-1111-1111-1111-111111111111",
        "paypal_order_id": "PAY-1",
        "mandate_id": "22222222-2222-2222-2222-222222222222",
    }


def _cart_row() -> dict:
    return {
        "mandate_hash": "hash-1",
        "intent_fit_verdict": None,
        "intent_fit_reason_code": None,
        "intent_fit_confidence": None,
        "lines": [
            {
                "sku": "sku-1",
                "qty": 2,
                "unit_price_minor": 1050,
                "line_total_minor": 2100,
                "merchant_id": "merchant-1",
            }
        ],
    }


def _mandate() -> dict:
    return {
        "status": "active",
        "remaining_minor": 9000,
        "protection": {
            "deliver_by_days": 14,
            "kinds_covered": [],
            "max_refund_minor": 5000,
        },
    }


def _receipt_text(receipt: dict) -> str:
    import json

    return json.dumps(receipt).lower()


def test_amount_major_never_uses_float() -> None:
    assert _amount_major(2100) == "21.00"
    assert _amount_major(5) == "0.05"
    assert _amount_major(0) == "0.00"


def test_receipt_contains_required_disclosure_phrase() -> None:
    receipt = _build_receipt_json(
        order_row=_order_row(),
        capture_id="CAP-1",
        amount_minor=2100,
        currency="USD",
        cart_row=_cart_row(),
        checks=[],
        mandate=_mandate(),
        event_id="33333333-3333-3333-3333-333333333333",
    )
    text = _receipt_text(receipt)
    assert REQUIRED_PHRASE in text


def test_receipt_never_contains_forbidden_claim_phrases() -> None:
    receipt = _build_receipt_json(
        order_row=_order_row(),
        capture_id="CAP-1",
        amount_minor=2100,
        currency="USD",
        cart_row=_cart_row(),
        checks=[
            {
                "name": "MERCHANT_ALLOWED",
                "result": "PASS",
                "reason_code": None,
                "source": "mandate",
                "detail": None,
            }
        ],
        mandate=_mandate(),
        event_id="33333333-3333-3333-3333-333333333333",
    )
    text = _receipt_text(receipt)
    for phrase in FORBIDDEN_CLAIM_PHRASES:
        assert phrase not in text, (
            f"forbidden claim phrase leaked into receipt: {phrase!r}"
        )


def test_receipt_amounts_are_major_units_derived_from_minor_not_float() -> None:
    receipt = _build_receipt_json(
        order_row=_order_row(),
        capture_id="CAP-1",
        amount_minor=2100,
        currency="USD",
        cart_row=_cart_row(),
        checks=[],
        mandate=_mandate(),
        event_id="33333333-3333-3333-3333-333333333333",
    )
    assert receipt["amount_minor"] == 2100
    assert receipt["amount_major"] == "21.00"
    assert isinstance(receipt["amount_major"], str)
    line = receipt["lines"][0]
    assert line["unit_minor"] == 1050
    assert line["unit_major"] == "10.50"
    assert line["line_minor"] == 2100
    assert line["line_major"] == "21.00"


def test_receipt_protection_window_from_mandate_terms_not_invented() -> None:
    receipt = _build_receipt_json(
        order_row=_order_row(),
        capture_id="CAP-1",
        amount_minor=2100,
        currency="USD",
        cart_row=_cart_row(),
        checks=[],
        mandate=_mandate(),
        event_id="33333333-3333-3333-3333-333333333333",
    )
    assert receipt["protection"]["window_days"] == 14
    assert receipt["protection"]["protected_until_day"] == 14
    assert receipt["protection"]["label"] == "Demo window, not PayPal's"


def test_receipt_mandate_and_audit_fields() -> None:
    receipt = _build_receipt_json(
        order_row=_order_row(),
        capture_id="CAP-1",
        amount_minor=2100,
        currency="USD",
        cart_row=_cart_row(),
        checks=[],
        mandate=_mandate(),
        event_id="33333333-3333-3333-3333-333333333333",
    )
    assert receipt["mandate"]["mandate_id"] == "22222222-2222-2222-2222-222222222222"
    assert receipt["mandate"]["mandate_hash"] == "hash-1"
    assert receipt["audit"]["event_id"] == "33333333-3333-3333-3333-333333333333"
    assert receipt["audit"]["seq"] is None
    assert receipt["remaining_cap_minor"] == 9000
