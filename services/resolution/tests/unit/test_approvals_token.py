"""Unit tests for the approval-link HMAC digest (app/usecases/approvals.py _digest).

Pure-function tests only (no DB, no app session) -- issue_approval/lookup_approval themselves
need a DB session and are covered by integration tests instead.
"""

from __future__ import annotations

from app.usecases.approvals import _digest


def test_digest_is_deterministic() -> None:
    key = b"test-key"
    a = _digest("tid-1", "hash-1", 1_700_000_000, key)
    b = _digest("tid-1", "hash-1", 1_700_000_000, key)
    assert a == b
    assert len(a) == 64  # sha256 hex


def test_digest_changes_with_proposal_hash() -> None:
    key = b"test-key"
    a = _digest("tid-1", "hash-1", 1_700_000_000, key)
    b = _digest("tid-1", "hash-2", 1_700_000_000, key)
    assert a != b


def test_digest_changes_with_tid() -> None:
    key = b"test-key"
    a = _digest("tid-1", "hash-1", 1_700_000_000, key)
    b = _digest("tid-2", "hash-1", 1_700_000_000, key)
    assert a != b


def test_digest_changes_with_expiry() -> None:
    key = b"test-key"
    a = _digest("tid-1", "hash-1", 1_700_000_000, key)
    b = _digest("tid-1", "hash-1", 1_700_000_001, key)
    assert a != b


def test_digest_changes_with_key() -> None:
    a = _digest("tid-1", "hash-1", 1_700_000_000, b"key-a")
    b = _digest("tid-1", "hash-1", 1_700_000_000, b"key-b")
    assert a != b
