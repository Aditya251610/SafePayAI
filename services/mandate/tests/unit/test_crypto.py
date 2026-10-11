"""canon.v1 determinism (MD-T* golden/property tests): same effective terms, even
with different key order or NFC form, must hash identically; different terms must
hash differently."""

from __future__ import annotations

import json

from app.crypto import canon_hash, canonical_json_bytes


def test_canonical_hash_is_key_order_independent():
    obj_a = {"b": 2, "a": 1, "c": {"y": 2, "x": 1}}
    obj_b = {"a": 1, "c": {"x": 1, "y": 2}, "b": 2}
    assert canon_hash(obj_a) == canon_hash(obj_b)


def test_canonical_hash_nfc_normalizes_strings():
    # "é" as a single NFC codepoint vs decomposed e + combining accent (NFD).
    nfc_form = {"name": "café"}
    nfd_form = {"name": "café"}
    assert canon_hash(nfc_form) == canon_hash(nfd_form)


def test_canonical_hash_changes_with_effective_terms():
    base = {"max_total_minor": 1000, "currency": "USD"}
    changed = {"max_total_minor": 1001, "currency": "USD"}
    assert canon_hash(base) != canon_hash(changed)


def test_canonical_bytes_are_compact_and_sorted():
    obj = {"z": 1, "a": 2}
    raw = canonical_json_bytes(obj)
    assert raw == b'{"a":2,"z":1}'
    # Round-trips through plain json too (canon.v1 is a strict subset of JSON).
    assert json.loads(raw) == obj


def test_canonical_json_rejects_float():
    import pytest

    from app.crypto import CanonError

    with pytest.raises(CanonError):
        canonical_json_bytes({"x": 1.5})


def test_canonical_json_rejects_null():
    import pytest

    from app.crypto import CanonError

    with pytest.raises(CanonError):
        canonical_json_bytes({"x": None})


def test_hmac_round_trip_and_tamper_detection():
    from app.crypto import MANDATE_HMAC_DOMAIN, compute_hmac, verify_hmac

    key = b"test-key-material-not-a-secret-just-for-unit-tests"
    h = compute_hmac(key, MANDATE_HMAC_DOMAIN, b"\x01" * 32, "buyer-1", "nonce-abc")
    assert verify_hmac(key, MANDATE_HMAC_DOMAIN, b"\x01" * 32, "buyer-1", "nonce-abc", h)
    assert not verify_hmac(key, MANDATE_HMAC_DOMAIN, b"\x02" * 32, "buyer-1", "nonce-abc", h)
    assert not verify_hmac(key, MANDATE_HMAC_DOMAIN, b"\x01" * 32, "buyer-2", "nonce-abc", h)
