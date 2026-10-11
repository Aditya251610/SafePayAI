"""L1 unit tests for app.ledger.body_sha256: deterministic hash used by the
IDEMPOTENCY_KEY_REUSED guard (spec.md section 6)."""

from __future__ import annotations

from app.ledger import body_sha256


def test_body_sha256_deterministic_regardless_of_key_order():
    a = body_sha256({"op": "create_order", "amount_minor": 4999, "currency": "USD"})
    b = body_sha256({"currency": "USD", "amount_minor": 4999, "op": "create_order"})
    assert a == b


def test_body_sha256_changes_with_amount():
    a = body_sha256({"op": "create_order", "amount_minor": 4999, "currency": "USD"})
    b = body_sha256({"op": "create_order", "amount_minor": 5000, "currency": "USD"})
    assert a != b
