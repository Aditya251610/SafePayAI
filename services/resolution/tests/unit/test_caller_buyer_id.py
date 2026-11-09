"""The buyer id comes from the gateway token's `sub`; a `buyer_id` claim wins when present."""

from __future__ import annotations

from app_resolution.routers.cases import caller_buyer_id


def test_sub_is_the_buyer_id_when_no_buyer_claim() -> None:
    assert (
        caller_buyer_id({"sub": "92465b75-0000", "act": {"role": "buyer"}})
        == "92465b75-0000"
    )


def test_explicit_buyer_id_claim_wins() -> None:
    assert caller_buyer_id({"sub": "svc", "buyer_id": "b-1"}) == "b-1"


def test_missing_identity_is_empty_never_matches_a_case() -> None:
    assert caller_buyer_id({}) == ""
