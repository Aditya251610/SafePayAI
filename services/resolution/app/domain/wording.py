"""Neutral-wording templates and the banned-word/URL/amount gate for buyer/merchant-visible text.

Implements resolution/spec.md section 11 (neutral wording and banned words) and CLAUDE.md's
honesty rules (never "flagged"/"suspicious"/"fraud"/"abuse" etc. in buyer-facing text). All
buyer-visible strings must come from the TEMPLATES below; any other text (including triage-ai
drafts) must pass `gate()` or fall back to a static template. Pure module: no I/O, no clock.
"""

from __future__ import annotations

import re
from enum import StrEnum

# Case-insensitive, stem-matched banned words (spec s11). Word-boundary regex so "lying" matches
# "lie"/"lying" via the stem but we don't false-positive on unrelated substrings.
_BANNED_STEMS: tuple[str, ...] = (
    "fraud",
    "fraudulent",
    "suspect",
    "suspected",
    "suspicious",
    "scam",
    "abuse",
    "abusive",
    "cheat",
    "dishonest",
    "lie",
    "lying",
    "accuse",
    "accusation",
    "violation",
    "flagged",
    "blacklist",
    "rejected",
    "denied",
)

_BANNED_PHRASES: tuple[str, ...] = ("your fault",)

_URL_PATTERN = re.compile(r"(https?://|www\.|://|\[.*?\]\(.*?\))", re.IGNORECASE)

# Matches a currency-looking amount: $12.34, 12.34 USD, etc. Amounts must come only from
# server-filled template slots, never from drafted free text (spec s11).
_AMOUNT_PATTERN = re.compile(
    r"(\$\s?\d|\d+\s?(\.\d{2})?\s?(usd|eur|gbp)\b)", re.IGNORECASE
)

_STEM_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(stem) for stem in _BANNED_STEMS) + r")\w*\b",
    re.IGNORECASE,
)


class WordingTemplateKey(StrEnum):
    """Keys into TEMPLATES (spec s11 reference templates)."""

    CHECKING = "CHECKING"
    LATE_OFFER = "LATE_OFFER"
    HUMAN_REVIEWING = "HUMAN_REVIEWING"
    REFUND_SENT = "REFUND_SENT"


TEMPLATES: dict[WordingTemplateKey, str] = {
    WordingTemplateKey.CHECKING: "We are checking your order.",
    WordingTemplateKey.LATE_OFFER: "Your order looks late. Here is an offer.",
    WordingTemplateKey.HUMAN_REVIEWING: "A person is reviewing your case; your coverage stays active.",
    WordingTemplateKey.REFUND_SENT: "Your refund was sent.",
}


class WordingViolation(StrEnum):
    """Why `gate()` rejected a string (spec s11)."""

    URL = "URL"
    AMOUNT = "AMOUNT"
    BANNED_WORD = "BANNED_WORD"


def gate(text: str) -> WordingViolation | None:
    """Return the first violation found in `text`, or None if it passes (spec s11).

    Inputs: any candidate buyer/merchant-visible string (e.g. a triage-ai draft).
    Output: None if the text may be shown as-is; otherwise the violation found. Callers must
    fall back to a static TEMPLATES entry on any violation (never partially sanitize).
    Edge cases: empty string passes; comparison is case-insensitive and stem-based.
    """
    if _URL_PATTERN.search(text):
        return WordingViolation.URL
    if _AMOUNT_PATTERN.search(text):
        return WordingViolation.AMOUNT
    if _STEM_PATTERN.search(text):
        return WordingViolation.BANNED_WORD
    for phrase in _BANNED_PHRASES:
        if phrase in text.lower():
            return WordingViolation.BANNED_WORD
    return None


def render(key: WordingTemplateKey) -> str:
    """Return the static template text for `key` (spec s11); the only buyer-visible text source."""
    return TEMPLATES[key]


def safe_text(candidate: str, fallback_key: WordingTemplateKey) -> str:
    """Return `candidate` if it passes the gate, else the static fallback template (spec s11)."""
    if gate(candidate) is None:
        return candidate
    return render(fallback_key)
