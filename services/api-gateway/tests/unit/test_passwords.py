from __future__ import annotations

from app.auth.passwords import hash_password, verify_password


def test_hash_and_verify_roundtrip():
    h = hash_password("correct-horse-battery-staple")
    assert verify_password("correct-horse-battery-staple", h) is True


def test_verify_rejects_wrong_password():
    h = hash_password("correct-horse-battery-staple")
    assert verify_password("something-else", h) is False


def test_verify_unknown_handle_dummy_path_always_false():
    assert verify_password("anything", None) is False
