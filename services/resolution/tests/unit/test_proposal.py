"""Unit tests for app/domain/proposal.py (spec s5 proposal_hash)."""

from __future__ import annotations

import uuid

from app.domain.proposal import Action, ProposalFields, hashes_match, proposal_hash


def _fields(**overrides: object) -> ProposalFields:
    defaults: dict[str, object] = {
        "case_id": uuid.UUID(int=1),
        "order_id": uuid.UUID(int=2),
        "capture_id": "cap-1",
        "mandate_id": "mandate-1",
        "terms_hash": "terms-hash",
        "policy_version": "v1",
        "action": Action.REFUND,
        "amount_minor": 1000,
        "currency": "USD",
        "offer_seq": 1,
    }
    defaults.update(overrides)
    return ProposalFields(**defaults)  # type: ignore[arg-type]


def test_proposal_hash_is_deterministic() -> None:
    a = proposal_hash(_fields())
    b = proposal_hash(_fields())
    assert a == b
    assert len(a) == 64


def test_proposal_hash_changes_with_amount() -> None:
    a = proposal_hash(_fields(amount_minor=1000))
    b = proposal_hash(_fields(amount_minor=1001))
    assert a != b


def test_proposal_hash_changes_with_action() -> None:
    a = proposal_hash(_fields(action=Action.REFUND))
    b = proposal_hash(_fields(action=Action.RESHIP))
    assert a != b


def test_proposal_hash_changes_with_offer_seq() -> None:
    a = proposal_hash(_fields(offer_seq=1))
    b = proposal_hash(_fields(offer_seq=2))
    assert a != b


def test_hashes_match_equal() -> None:
    h = proposal_hash(_fields())
    assert hashes_match(h, h)


def test_hashes_match_different_length_is_false() -> None:
    assert not hashes_match("abc", "abcd")


def test_hashes_match_different_value_is_false() -> None:
    assert not hashes_match("a" * 64, "b" * 64)
