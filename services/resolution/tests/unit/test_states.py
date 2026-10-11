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
