"""Unit tests for app/domain/policy.py (spec s4 decision table D0-D10, P1-P3 rules).

Money-path core logic: every row of the decision table gets at least one test, plus boundary
tests for the three illustrative policies (spec sprint S3-04 calls these out explicitly).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app_resolution.domain.policy import (
    CaptureFacts,
    DecisionFacts,
    PolicyClass,
    PolicyConfig,
    ReasonCode,
    TermsSnapshot,
    config_from_settings,
    decide,
    rule_buyer_velocity,
    rule_category_exclusion,
    rule_refund_cap,
)
from app_resolution.domain.states import CaseKind

CFG = PolicyConfig(
    policy_version="v1",
    refund_cap_minor=5000,
    excluded_categories=frozenset({"restricted"}),
    velocity_max=2,
    velocity_window_days=30,
    triage_min_confidence=0.7,
)
NOW = datetime(2026, 1, 10, tzinfo=UTC)
OPENED_AT = datetime(2026, 1, 5, tzinfo=UTC)
PROTECTED_UNTIL = datetime(2026, 2, 1, tzinfo=UTC)

TERMS = TermsSnapshot(
    kinds_covered=frozenset({CaseKind.LATE, CaseKind.LOST}),
    max_refund_minor=10000,
    window_hold_days=30,
    rule="FULL_ORDER",
)
CAPTURE = CaptureFacts(
    capture_id="cap-1",
    status="COMPLETED",
    amount_minor=2000,
    refunded_total_minor=0,
    currency="USD",
)


def _facts(**overrides: object) -> DecisionFacts:
    defaults: dict[str, object] = {
        "kind": CaseKind.LATE,
        "triage_ok": True,
        "triage_confidence": 0.9,
        "injection_suspected": False,
        "carrier_status": "IN_TRANSIT",
        "carrier_agrees": True,
        "terms": TERMS,
        "mandate_hash_valid": True,
        "protected_until": PROTECTED_UNTIL,
        "case_opened_at": OPENED_AT,
        "now": NOW,
        "capture": CAPTURE,
        "item_categories": frozenset(),
        "buyer_completed_refunds_in_window": 0,
    }
    defaults.update(overrides)
    return DecisionFacts(**defaults)  # type: ignore[arg-type]


# --- P1/P2/P3 rule unit tests (boundary values, sprint S3-04) ---------------------------------


def test_rule_refund_cap_boundary_equal_is_not_a_hit() -> None:
    assert rule_refund_cap(5000, CFG) is None


def test_rule_refund_cap_over_is_a_hit() -> None:
    assert rule_refund_cap(5001, CFG) == ReasonCode.POLICY_CAP


def test_rule_category_exclusion_hit() -> None:
    assert (
        rule_category_exclusion(frozenset({"restricted"}), CFG)
        == ReasonCode.POLICY_CATEGORY
    )


def test_rule_category_exclusion_no_hit_on_empty() -> None:
    assert rule_category_exclusion(frozenset(), CFG) is None


def test_rule_velocity_boundary_two_allowed() -> None:
    assert rule_buyer_velocity(2, CFG) is None


def test_rule_velocity_three_triggers() -> None:
    assert rule_buyer_velocity(3, CFG) == ReasonCode.POLICY_VELOCITY


def test_rule_velocity_none_is_not_a_hit_itself() -> None:
    """rule_buyer_velocity(None, ...) returns None; decide() maps None to D0, not a P3 hit."""
    assert rule_buyer_velocity(None, CFG) is None


# --- Decision table D0-D10 ----------------------------------------------------------------------


def test_d0_missing_terms_is_human_review() -> None:
    decision = decide(_facts(terms=None), CFG)
    assert decision.klass == PolicyClass.HUMAN_REVIEW
    assert decision.reasons[0].code == ReasonCode.FACT_UNAVAILABLE


def test_d0_missing_capture_is_human_review() -> None:
    decision = decide(_facts(capture=None), CFG)
    assert decision.klass == PolicyClass.HUMAN_REVIEW
    assert decision.reasons[0].code == ReasonCode.FACT_UNAVAILABLE


def test_d0_missing_velocity_count_is_human_review() -> None:
    decision = decide(_facts(buyer_completed_refunds_in_window=None), CFG)
    assert decision.klass == PolicyClass.HUMAN_REVIEW
    assert decision.reasons[0].code == ReasonCode.FACT_UNAVAILABLE


def test_d0_invalid_mandate_hash_is_human_review() -> None:
    decision = decide(_facts(mandate_hash_valid=False), CFG)
    assert decision.klass == PolicyClass.HUMAN_REVIEW
    assert decision.reasons[0].code == ReasonCode.TERMS_INVALID


def test_d0_missing_carrier_agreement_for_late_claim() -> None:
    decision = decide(_facts(carrier_agrees=None), CFG)
    assert decision.klass == PolicyClass.HUMAN_REVIEW
    assert decision.reasons[0].code == ReasonCode.FACT_UNAVAILABLE


def test_d0_missing_protected_until_for_late_claim() -> None:
    decision = decide(_facts(protected_until=None), CFG)
    assert decision.klass == PolicyClass.HUMAN_REVIEW
    assert decision.reasons[0].code == ReasonCode.FACT_UNAVAILABLE


def test_unsupported_terms_rule_is_human_review() -> None:
    bad_terms = TermsSnapshot(
        kinds_covered=TERMS.kinds_covered,
        max_refund_minor=TERMS.max_refund_minor,
        window_hold_days=TERMS.window_hold_days,
        rule="PER_ITEM",
    )
    decision = decide(_facts(terms=bad_terms), CFG)
    assert decision.klass == PolicyClass.HUMAN_REVIEW
    assert decision.reasons[0].code == ReasonCode.UNSUPPORTED_TERMS


def test_d1_triage_not_ok_is_human_review() -> None:
    decision = decide(_facts(triage_ok=False), CFG)
    assert decision.klass == PolicyClass.HUMAN_REVIEW
    assert decision.reasons[0].code == ReasonCode.TRIAGE_FAIL_CLOSED


def test_d1_low_confidence_is_human_review() -> None:
    decision = decide(_facts(triage_confidence=0.5), CFG)
    assert decision.klass == PolicyClass.HUMAN_REVIEW
    assert decision.reasons[0].code == ReasonCode.TRIAGE_FAIL_CLOSED


def test_d1_injection_suspected_is_human_review() -> None:
    decision = decide(_facts(injection_suspected=True), CFG)
    assert decision.klass == PolicyClass.HUMAN_REVIEW
    assert decision.reasons[0].code == ReasonCode.TRIAGE_FAIL_CLOSED


def test_d2_kind_other_is_human_review() -> None:
    decision = decide(_facts(kind=CaseKind.OTHER), CFG)
    assert decision.klass == PolicyClass.HUMAN_REVIEW
    assert decision.reasons[0].code == ReasonCode.KIND_OTHER


def test_d3_carrier_disagrees_is_human_review() -> None:
    decision = decide(_facts(carrier_agrees=False), CFG)
    assert decision.klass == PolicyClass.HUMAN_REVIEW
    assert decision.reasons[0].code == ReasonCode.CARRIER_DISAGREES


def test_d4_category_excluded_is_human_review() -> None:
    decision = decide(_facts(item_categories=frozenset({"restricted"})), CFG)
    assert decision.klass == PolicyClass.HUMAN_REVIEW
    assert decision.reasons[0].code == ReasonCode.POLICY_CATEGORY


def test_d5_velocity_exceeded_is_human_review() -> None:
    decision = decide(_facts(buyer_completed_refunds_in_window=3), CFG)
    assert decision.klass == PolicyClass.HUMAN_REVIEW
    assert decision.reasons[0].code == ReasonCode.POLICY_VELOCITY


def test_d6_amount_over_cap_is_human_review() -> None:
    big_capture = CaptureFacts(
        capture_id="cap-1",
        status="COMPLETED",
        amount_minor=6000,
        refunded_total_minor=0,
        currency="USD",
    )
    decision = decide(_facts(capture=big_capture), CFG)
    assert decision.klass == PolicyClass.HUMAN_REVIEW
    assert decision.reasons[0].code == ReasonCode.POLICY_CAP


def test_d7_evidence_kinds_are_human_review() -> None:
    for kind in (CaseKind.DAMAGED, CaseKind.WRONG_ITEM, CaseKind.NOT_AS_DESCRIBED):
        decision = decide(_facts(kind=kind), CFG)
        assert decision.klass == PolicyClass.HUMAN_REVIEW
        assert decision.reasons[0].code == ReasonCode.NEEDS_EVIDENCE


def test_d8_inside_terms_happy_path() -> None:
    decision = decide(_facts(), CFG)
    assert decision.klass == PolicyClass.INSIDE_TERMS
    assert decision.reasons[0].code == ReasonCode.IN_TERMS
    assert decision.amount_minor == 2000
    assert decision.currency == "USD"


def test_d9_outside_terms_amount() -> None:
    narrow_terms = TermsSnapshot(
        kinds_covered=TERMS.kinds_covered,
        max_refund_minor=100,
        window_hold_days=TERMS.window_hold_days,
        rule="FULL_ORDER",
    )
    decision = decide(_facts(terms=narrow_terms), CFG)
    assert decision.klass == PolicyClass.OUTSIDE_TERMS
    assert decision.reasons[0].code == ReasonCode.OUT_OF_TERMS_AMOUNT


def test_d9_outside_terms_kind_not_covered() -> None:
    narrow_terms = TermsSnapshot(
        kinds_covered=frozenset({CaseKind.LOST}),
        max_refund_minor=TERMS.max_refund_minor,
        window_hold_days=TERMS.window_hold_days,
        rule="FULL_ORDER",
    )
    decision = decide(_facts(kind=CaseKind.LATE, terms=narrow_terms), CFG)
    assert decision.klass == PolicyClass.OUTSIDE_TERMS
    assert decision.reasons[0].code == ReasonCode.OUT_OF_TERMS_KIND


def test_d9_outside_terms_window() -> None:
    decision = decide(_facts(protected_until=OPENED_AT - timedelta(days=1)), CFG)
    assert decision.klass == PolicyClass.OUTSIDE_TERMS
    assert decision.reasons[0].code == ReasonCode.OUT_OF_TERMS_WINDOW


def test_decide_is_deterministic_same_inputs_same_decision() -> None:
    facts = _facts()
    a = decide(facts, CFG)
    b = decide(facts, CFG)
    assert a.klass == b.klass
    assert a.reasons == b.reasons
    assert a.facts_hash == b.facts_hash


def test_decide_never_denies() -> None:
    """Outcomes never include a denial (spec s4) - klass is always one of the 3 named values."""
    for kind in CaseKind:
        decision = decide(_facts(kind=kind), CFG)
        assert decision.klass in (
            PolicyClass.INSIDE_TERMS,
            PolicyClass.OUTSIDE_TERMS,
            PolicyClass.HUMAN_REVIEW,
        )


def test_config_from_settings_builds_policy_config() -> None:
    cfg = config_from_settings(
        {
            "policy_version": "v2",
            "refund_cap_minor": 1234,
            "excluded_categories": "a, b,",
            "velocity_max": 3,
            "velocity_window_days": 14,
            "triage_min_confidence": 0.5,
        }
    )
    assert cfg.policy_version == "v2"
    assert cfg.refund_cap_minor == 1234
    assert cfg.excluded_categories == frozenset({"a", "b"})
    assert cfg.velocity_max == 3


def test_config_from_settings_missing_key_raises() -> None:
    import pytest

    with pytest.raises(KeyError):
        config_from_settings({})
