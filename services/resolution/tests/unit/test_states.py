"""Unit tests for app/domain/states.py (spec s3, transition table T1-T27)."""

from __future__ import annotations

from app.domain.states import CaseState, is_legal_transition


def test_offered_self_loop_legal_merchant_override() -> None:
    assert is_legal_transition(CaseState.OFFERED, CaseState.OFFERED)


def test_human_review_self_loop_legal_escalation() -> None:
    assert is_legal_transition(CaseState.HUMAN_REVIEW, CaseState.HUMAN_REVIEW)


def test_terminal_states_have_no_exits() -> None:
    assert not is_legal_transition(CaseState.RESOLVED_REFUNDED, CaseState.OFFERED)
    assert is_legal_transition(CaseState.RESOLVED_REFUNDED, CaseState.CLOSED)
    assert not is_legal_transition(CaseState.CLOSED, CaseState.OFFERED)


def test_approved_to_refunding_legal_t16() -> None:
    assert is_legal_transition(CaseState.APPROVED, CaseState.REFUNDING)


def test_refunding_to_approved_legal_t20_frozen() -> None:
    assert is_legal_transition(CaseState.REFUNDING, CaseState.APPROVED)


def test_declined_to_offered_legal_merchant_override_t25() -> None:
    assert is_legal_transition(CaseState.DECLINED, CaseState.OFFERED)


def test_no_system_driven_transition_into_declined_from_protected() -> None:
    assert not is_legal_transition(CaseState.PROTECTED, CaseState.DECLINED)


def test_illegal_skip_from_protected_to_approved() -> None:
    assert not is_legal_transition(CaseState.PROTECTED, CaseState.APPROVED)


def test_human_review_to_offered_legal_t13_reviewer_propose() -> None:
    assert is_legal_transition(CaseState.HUMAN_REVIEW, CaseState.OFFERED)


def test_human_review_to_declined_legal_t14_reviewer_decline() -> None:
    assert is_legal_transition(CaseState.HUMAN_REVIEW, CaseState.DECLINED)


def test_human_review_to_closed_legal_t15_reviewer_close() -> None:
    assert is_legal_transition(CaseState.HUMAN_REVIEW, CaseState.CLOSED)


def test_declined_to_human_review_legal_t24_buyer_appeal() -> None:
    assert is_legal_transition(CaseState.DECLINED, CaseState.HUMAN_REVIEW)


def test_offered_to_resolved_reship_legal_t10() -> None:
    assert is_legal_transition(CaseState.OFFERED, CaseState.RESOLVED_RESHIP)


def test_offered_to_human_review_legal_t12_offer_expired() -> None:
    assert is_legal_transition(CaseState.OFFERED, CaseState.HUMAN_REVIEW)


def test_resolved_refunded_to_closed_legal_t21() -> None:
    assert is_legal_transition(CaseState.RESOLVED_REFUNDED, CaseState.CLOSED)


def test_resolved_reship_to_closed_legal_t22() -> None:
    assert is_legal_transition(CaseState.RESOLVED_RESHIP, CaseState.CLOSED)


def test_declined_to_closed_legal_t23_appeal_window_elapsed() -> None:
    assert is_legal_transition(CaseState.DECLINED, CaseState.CLOSED)


def test_closed_is_terminal_no_appeal_after_close() -> None:
    assert not is_legal_transition(CaseState.CLOSED, CaseState.HUMAN_REVIEW)
