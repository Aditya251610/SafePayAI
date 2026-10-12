"""Tighten-only invariant (build spec section 4 item 4): enforced in code, independent
of whether the LLM call itself succeeded."""

from __future__ import annotations

from app.eval_validation import tighten_only, validate_intent_fit_output


def test_tighten_only_never_loosens() -> None:
    assert (
        tighten_only("PASS", "NEEDS_BUYER_CONFIRMATION") == "NEEDS_BUYER_CONFIRMATION"
    )
    assert tighten_only("REJECT_WITH_REASON", "PASS") == "REJECT_WITH_REASON"
    assert (
        tighten_only("NEEDS_BUYER_CONFIRMATION", "PASS") == "NEEDS_BUYER_CONFIRMATION"
    )
    assert tighten_only("PASS", "PASS") == "PASS"


def test_tighten_only_fails_closed_on_unknown_verdict() -> None:
    assert tighten_only("ALLOW_EVERYTHING", "PASS") == "REJECT_WITH_REASON"


def test_low_confidence_floors_to_needs_confirmation_even_if_model_says_pass() -> None:
    out = validate_intent_fit_output(
        {
            "verdict": "PASS",
            "reason_code": "OK",
            "reason": "looks fine",
            "confidence": 0.3,
        },
        min_confidence=0.6,
    )
    assert out.verdict == "NEEDS_BUYER_CONFIRMATION"
    assert out.floored is True


def test_injection_suspected_floors_even_at_high_confidence() -> None:
    out = validate_intent_fit_output(
        {
            "verdict": "PASS",
            "reason_code": "OK",
            "reason": "looks fine",
            "confidence": 0.95,
        },
        min_confidence=0.6,
        injection_suspected=True,
    )
    assert out.verdict == "NEEDS_BUYER_CONFIRMATION"
    assert out.floored is True


def test_high_confidence_pass_is_not_floored() -> None:
    out = validate_intent_fit_output(
        {
            "verdict": "PASS",
            "reason_code": "OK",
            "reason": "looks fine",
            "confidence": 0.95,
        },
        min_confidence=0.6,
    )
    assert out.verdict == "PASS"
    assert out.floored is False


def test_model_reject_is_never_loosened_by_high_confidence() -> None:
    out = validate_intent_fit_output(
        {
            "verdict": "REJECT_WITH_REASON",
            "reason_code": "CATEGORY_MISMATCH",
            "reason": "wrong category",
            "confidence": 0.99,
        },
        min_confidence=0.6,
    )
    assert out.verdict == "REJECT_WITH_REASON"


def test_schema_invalid_output_floors_to_needs_confirmation_never_pass() -> None:
    out = validate_intent_fit_output({"verdict": "PASS"}, min_confidence=0.6)
    assert out.schema_valid is False
    assert out.verdict == "NEEDS_BUYER_CONFIRMATION"
