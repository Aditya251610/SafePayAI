"""Unit tests for app/domain/wording.py (spec s11 + CLAUDE.md honesty rules banned-word gate)."""

from __future__ import annotations

import pytest

from app.domain.wording import (
    WordingTemplateKey,
    WordingViolation,
    gate,
    render,
    safe_text,
)

BANNED_EXAMPLES = [
    "This looks suspicious to us.",
    "We think this is fraud.",
    "Your claim was flagged for review.",
    "This account shows signs of abuse.",
    "Your refund was denied.",
    "Your request was rejected.",
    "That is your fault.",
]


@pytest.mark.parametrize("text", BANNED_EXAMPLES)
def test_gate_rejects_banned_words(text: str) -> None:
    assert gate(text) == WordingViolation.BANNED_WORD


def test_gate_rejects_urls() -> None:
    assert gate("Click http://example.com to continue") == WordingViolation.URL
    assert gate("Visit www.example.com") == WordingViolation.URL
    assert gate("See [here](http://evil.com)") == WordingViolation.URL


def test_gate_rejects_amounts() -> None:
    assert gate("We will refund $12.34 today") == WordingViolation.AMOUNT
    assert gate("Amount: 12.34 USD") == WordingViolation.AMOUNT


def test_gate_passes_neutral_text() -> None:
    assert gate("We are checking your order.") is None
    assert gate("A person is reviewing your case; your coverage stays active.") is None


def test_safe_text_falls_back_on_violation() -> None:
    result = safe_text("Your claim looks suspicious.", WordingTemplateKey.CHECKING)
    assert result == render(WordingTemplateKey.CHECKING)


def test_safe_text_passes_through_clean_text() -> None:
    clean = "We are checking your order."
    assert safe_text(clean, WordingTemplateKey.CHECKING) == clean


def test_render_returns_reference_templates() -> None:
    assert render(WordingTemplateKey.REFUND_SENT) == "Your refund was sent."
