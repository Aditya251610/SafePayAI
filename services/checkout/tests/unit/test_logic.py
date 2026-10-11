from __future__ import annotations

from app.logic import CheckResult, combine_status, compute_proposal_hash


def test_combine_status_checked_when_all_pass() -> None:
    checks = [CheckResult("catalog", "PASS", None, "catalog")]
    assert combine_status(checks, intent_fit_verdict=None) == "CHECKED"


def test_combine_status_blocked_on_any_hard_block() -> None:
    checks = [
        CheckResult("catalog", "PASS", None, "catalog"),
        CheckResult("mandate", "BLOCK", "OVER_CAP", "mandate"),
    ]
    assert combine_status(checks, intent_fit_verdict=None) == "BLOCKED"


def test_combine_status_needs_confirmation_on_tighten_verdict() -> None:
    checks = [CheckResult("catalog", "PASS", None, "catalog")]
    assert (
        combine_status(checks, intent_fit_verdict="NEEDS_BUYER_CONFIRMATION")
        == "NEEDS_CONFIRMATION"
    )


def test_combine_status_blocked_wins_over_intent_fit() -> None:
    """Nothing moves BLOCKED to allowed - the agent's advisory verdict never overrides
    a hard block (spec.md section 4 step 9)."""
    checks = [CheckResult("mandate", "BLOCK", "MANDATE_REVOKED", "mandate")]
    assert combine_status(checks, intent_fit_verdict="PASS") == "BLOCKED"


def test_combine_status_reject_with_reason_blocks() -> None:
    checks: list[CheckResult] = []
    assert combine_status(checks, intent_fit_verdict="REJECT_WITH_REASON") == "BLOCKED"


def test_proposal_hash_deterministic() -> None:
    kwargs = {
        "mandate_id": "m1",
        "mandate_hash": "h1",
        "lines": [{"sku": "sku-b", "qty": 2}, {"sku": "sku-a", "qty": 1}],
        "total_minor": 500,
        "currency": "USD",
        "merchant_ids": ["merchant-2", "merchant-1"],
        "policy_version": "v1",
    }
    assert compute_proposal_hash(**kwargs) == compute_proposal_hash(**kwargs)


def test_proposal_hash_order_independent() -> None:
    """Line order and merchant_id order must not change the hash - both are sorted
    before hashing (spec.md section 4 step 10 says "sorted (sku, qty)")."""
    h1 = compute_proposal_hash(
        mandate_id="m1",
        mandate_hash="h1",
        lines=[{"sku": "a", "qty": 1}, {"sku": "b", "qty": 2}],
        total_minor=500,
        currency="USD",
        merchant_ids=["m1", "m2"],
        policy_version="v1",
    )
    h2 = compute_proposal_hash(
        mandate_id="m1",
        mandate_hash="h1",
        lines=[{"sku": "b", "qty": 2}, {"sku": "a", "qty": 1}],
        total_minor=500,
        currency="USD",
        merchant_ids=["m2", "m1"],
        policy_version="v1",
    )
    assert h1 == h2


def test_proposal_hash_changes_with_total() -> None:
    base = {
        "mandate_id": "m1",
        "mandate_hash": "h1",
        "lines": [{"sku": "a", "qty": 1}],
        "currency": "USD",
        "merchant_ids": ["m1"],
        "policy_version": "v1",
    }
    h1 = compute_proposal_hash(total_minor=500, **base)
    h2 = compute_proposal_hash(total_minor=600, **base)
    assert h1 != h2
