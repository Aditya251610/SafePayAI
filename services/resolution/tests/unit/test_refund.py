"""Unit tests for app/domain/refund.py (spec s7, s8 attempt state machine)."""

from __future__ import annotations

from app_resolution.domain.refund import (
    RefundAttemptStatus,
    is_legal_attempt_transition,
)


def test_requested_to_sent_legal() -> None:
    assert is_legal_attempt_transition(
        RefundAttemptStatus.REQUESTED, RefundAttemptStatus.SENT
    )


def test_requested_to_not_sent_legal() -> None:
    assert is_legal_attempt_transition(
        RefundAttemptStatus.REQUESTED, RefundAttemptStatus.NOT_SENT
    )


def test_unknown_to_sent_legal_reconcile_path() -> None:
    assert is_legal_attempt_transition(
        RefundAttemptStatus.UNKNOWN, RefundAttemptStatus.SENT
    )


def test_terminal_states_have_no_exits() -> None:
    for terminal in (
        RefundAttemptStatus.COMPLETED,
        RefundAttemptStatus.FAILED,
        RefundAttemptStatus.NOT_SENT,
    ):
        for target in RefundAttemptStatus:
            assert not is_legal_attempt_transition(terminal, target)


def test_requested_cannot_jump_to_completed() -> None:
    assert not is_legal_attempt_transition(
        RefundAttemptStatus.REQUESTED, RefundAttemptStatus.COMPLETED
    )
