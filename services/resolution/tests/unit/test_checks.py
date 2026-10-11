"""Unit tests for app/domain/checks.py (spec s6, the 9 ordered pre-refund checks, 1-8 pure)."""

from __future__ import annotations

from app.domain.checks import (
    AmountFacts,
    AuthorizationFacts,
    CaptureIdentityFacts,
    KillSwitchFacts,
    PolicyReevaluationFacts,
    PriorMoneyActionFacts,
    ProblemStillTrueFacts,
    TermsIntegrityFacts,
    check_amount_bounds,
    check_authorization_valid,
    check_capture_identity,
    check_kill_switch,
    check_no_prior_money_action,
    check_policy_reevaluation,
    check_problem_still_true,
    check_terms_integrity,
)


def test_check_kill_switch_passes_when_false() -> None:
    assert check_kill_switch(KillSwitchFacts(refunds_frozen=False)).passed


def test_check_kill_switch_fails_when_true() -> None:
    assert not check_kill_switch(KillSwitchFacts(refunds_frozen=True)).passed


def test_check_kill_switch_fails_when_unreadable() -> None:
    assert not check_kill_switch(KillSwitchFacts(refunds_frozen=None)).passed


def test_check_kill_switch_fails_on_mandate_or_merchant_freeze() -> None:
    assert not check_kill_switch(
        KillSwitchFacts(refunds_frozen=False, mandate_frozen=True)
    ).passed
    assert not check_kill_switch(
        KillSwitchFacts(refunds_frozen=False, merchant_frozen=True)
    ).passed


def test_check_authorization_valid_requires_approved_state() -> None:
    facts = AuthorizationFacts(
        case_state="OFFERED",
        approval_basis_present=True,
        offer_active=True,
        stored_hash_matches=True,
    )
    assert not check_authorization_valid(facts).passed


def test_check_authorization_valid_requires_hash_match() -> None:
    facts = AuthorizationFacts(
        case_state="APPROVED",
        approval_basis_present=True,
        offer_active=True,
        stored_hash_matches=False,
    )
    assert not check_authorization_valid(facts).passed


def test_check_authorization_valid_passes() -> None:
    facts = AuthorizationFacts(
        case_state="APPROVED",
        approval_basis_present=True,
        offer_active=True,
        stored_hash_matches=True,
    )
    assert check_authorization_valid(facts).passed


def test_check_terms_integrity_fails_when_mandate_unreachable() -> None:
    facts = TermsIntegrityFacts(
        fresh_terms_hash=None,
        fresh_terms_hmac_valid=False,
        stored_terms_hash="x",
        decision_policy_version="v1",
        current_policy_version="v1",
    )
    result = check_terms_integrity(facts)
    assert not result.passed
    assert result.detail_code == "MANDATE_UNREACHABLE"


def test_check_terms_integrity_fails_on_hash_mismatch() -> None:
    facts = TermsIntegrityFacts(
        fresh_terms_hash="y",
        fresh_terms_hmac_valid=True,
        stored_terms_hash="x",
        decision_policy_version="v1",
        current_policy_version="v1",
    )
    assert not check_terms_integrity(facts).passed


def test_check_terms_integrity_passes() -> None:
    facts = TermsIntegrityFacts(
        fresh_terms_hash="x",
        fresh_terms_hmac_valid=True,
        stored_terms_hash="x",
        decision_policy_version="v1",
        current_policy_version="v1",
    )
    assert check_terms_integrity(facts).passed


def test_check_capture_identity_fails_on_status() -> None:
    facts = CaptureIdentityFacts(
        capture_order_matches=True,
        custom_id_matches_mandate=True,
        capture_status="REFUNDED",
        capture_currency="USD",
        proposal_currency="USD",
    )
    assert not check_capture_identity(facts).passed


def test_check_capture_identity_fails_on_currency_mismatch() -> None:
    facts = CaptureIdentityFacts(
        capture_order_matches=True,
        custom_id_matches_mandate=True,
        capture_status="COMPLETED",
        capture_currency="EUR",
        proposal_currency="USD",
    )
    assert not check_capture_identity(facts).passed


def test_check_capture_identity_passes_partially_refunded() -> None:
    facts = CaptureIdentityFacts(
        capture_order_matches=True,
        custom_id_matches_mandate=True,
        capture_status="PARTIALLY_REFUNDED",
        capture_currency="USD",
        proposal_currency="USD",
    )
    assert check_capture_identity(facts).passed


def test_check_amount_bounds_fails_on_non_positive() -> None:
    facts = AmountFacts(
        proposal_amount_minor=0,
        requested_amount_minor=0,
        remaining_refundable_minor=1000,
        terms_max_refund_minor=1000,
        explicit_buyer_approval_or_override=False,
        adapter_per_call_ceiling_minor=100000,
    )
    assert not check_amount_bounds(facts).passed


def test_check_amount_bounds_fails_when_not_equal_proposal() -> None:
    facts = AmountFacts(
        proposal_amount_minor=500,
        requested_amount_minor=600,
        remaining_refundable_minor=1000,
        terms_max_refund_minor=1000,
        explicit_buyer_approval_or_override=False,
        adapter_per_call_ceiling_minor=100000,
    )
    assert not check_amount_bounds(facts).passed


def test_check_amount_bounds_fails_over_remaining_refundable() -> None:
    facts = AmountFacts(
        proposal_amount_minor=1200,
        requested_amount_minor=1200,
        remaining_refundable_minor=1000,
        terms_max_refund_minor=2000,
        explicit_buyer_approval_or_override=False,
        adapter_per_call_ceiling_minor=100000,
    )
    assert not check_amount_bounds(facts).passed


def test_check_amount_bounds_fails_over_terms_max_without_override() -> None:
    facts = AmountFacts(
        proposal_amount_minor=1500,
        requested_amount_minor=1500,
        remaining_refundable_minor=2000,
        terms_max_refund_minor=1000,
        explicit_buyer_approval_or_override=False,
        adapter_per_call_ceiling_minor=100000,
    )
    assert not check_amount_bounds(facts).passed


def test_check_amount_bounds_passes_over_terms_max_with_override() -> None:
    facts = AmountFacts(
        proposal_amount_minor=1500,
        requested_amount_minor=1500,
        remaining_refundable_minor=2000,
        terms_max_refund_minor=1000,
        explicit_buyer_approval_or_override=True,
        adapter_per_call_ceiling_minor=100000,
    )
    assert check_amount_bounds(facts).passed


def test_check_amount_bounds_fails_over_adapter_ceiling() -> None:
    facts = AmountFacts(
        proposal_amount_minor=1500,
        requested_amount_minor=1500,
        remaining_refundable_minor=2000,
        terms_max_refund_minor=2000,
        explicit_buyer_approval_or_override=True,
        adapter_per_call_ceiling_minor=1000,
    )
    assert not check_amount_bounds(facts).passed


def test_check_amount_bounds_passes() -> None:
    facts = AmountFacts(
        proposal_amount_minor=500,
        requested_amount_minor=500,
        remaining_refundable_minor=1000,
        terms_max_refund_minor=1000,
        explicit_buyer_approval_or_override=False,
        adapter_per_call_ceiling_minor=100000,
    )
    assert check_amount_bounds(facts).passed


def test_check_policy_reevaluation_fails_on_class_change() -> None:
    facts = PolicyReevaluationFacts(
        fresh_klass="HUMAN_REVIEW",
        offer_klass="INSIDE_TERMS",
        is_merchant_override=False,
        decision_policy_version="v1",
        current_policy_version="v1",
    )
    assert not check_policy_reevaluation(facts).passed


def test_check_policy_reevaluation_merchant_override_bypasses_class_check() -> None:
    facts = PolicyReevaluationFacts(
        fresh_klass="HUMAN_REVIEW",
        offer_klass="INSIDE_TERMS",
        is_merchant_override=True,
        decision_policy_version="v1",
        current_policy_version="v1",
    )
    assert check_policy_reevaluation(facts).passed


def test_check_no_prior_money_action_fails_when_attempt_exists() -> None:
    facts = PriorMoneyActionFacts(
        attempt_exists_for_case=True, live_attempt_exists_for_order=False
    )
    assert not check_no_prior_money_action(facts).passed


def test_check_no_prior_money_action_passes_when_clean() -> None:
    facts = PriorMoneyActionFacts(
        attempt_exists_for_case=False, live_attempt_exists_for_order=False
    )
    assert check_no_prior_money_action(facts).passed


def test_check_problem_still_true_fails_when_delivered() -> None:
    facts = ProblemStillTrueFacts(
        kind="LATE", carrier_status="DELIVERED", window_held=True
    )
    assert not check_problem_still_true(facts).passed


def test_check_problem_still_true_fails_when_window_not_held() -> None:
    facts = ProblemStillTrueFacts(
        kind="LATE", carrier_status="IN_TRANSIT", window_held=False
    )
    assert not check_problem_still_true(facts).passed


def test_check_problem_still_true_passes() -> None:
    facts = ProblemStillTrueFacts(
        kind="LATE", carrier_status="IN_TRANSIT", window_held=True
    )
    assert check_problem_still_true(facts).passed


def test_check_problem_still_true_ignores_carrier_for_non_shipping_kinds() -> None:
    facts = ProblemStillTrueFacts(kind="DAMAGED", carrier_status=None, window_held=True)
    assert check_problem_still_true(facts).passed
