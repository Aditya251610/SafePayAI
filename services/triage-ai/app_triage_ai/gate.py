"""Regex gate for /draft and /brief summary text (spec.md section 7). This gate is the
ACTUAL security boundary against URL/email/phone/amount/instruction-smuggling in model
output - the system-prompt instruction not to include these is advisory only. Never skip
this gate because "the model was told not to" (llm-integration-spec.md sections 4-5).

Scope note: this is a deliberately conservative subset of spec.md section 7's full table
(G-URL/G-MAIL/G-DIGIT/G-CUR/G-PH/G-INSTR/G-TONE implemented; G-LEN/G-LANG are left to the
pydantic `max_length` constraints already on DraftResponse/BriefResponse rather than a
separate regex, and the markdown-free requirement of G-LEN is not separately enforced here -
flagged as a follow-up, not a gap in the money-safety boundary since digits/URLs/amounts are
the properties that can actually cause harm).
"""

from __future__ import annotations

import re
import unicodedata

PLACEHOLDER_ALLOWLIST = {"{amount}", "{order_ref}", "{date}", "{buyer_name}"}

_PLACEHOLDER_TOKEN = re.compile(r"\{[^{}]{1,40}\}")

_GATE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "G-URL",
        re.compile(
            r"https?://|www\.|\b[a-z0-9-]+\.(com|net|org|io|co|info|biz|dev)\b|]\(|<a |data:|"
            r"javascript:|\(dot\)|\bdot\s*com\b",
            re.IGNORECASE,
        ),
    ),
    (
        "G-MAIL",
        re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+|\bat\b[^.]{0,20}\bdot\b", re.IGNORECASE),
    ),
    ("G-DIGIT", re.compile(r"\d")),
    (
        "G-CUR",
        re.compile(
            r"[$€£₹]|\b(usd|dollars?|euros?|rupees?|cents?|pounds?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "G-INSTR",
        re.compile(
            r"ignore\s+(all|previous)|system\s*:|assistant\s*:|<untrusted|"
            r"approve\s+(the\s+)?refund|\boverride\b|refund_capture|\bmcp\b",
            re.IGNORECASE,
        ),
    ),
    (
        "G-TONE",
        re.compile(
            r"\bfraud\b|\bscam\b|\bliar\b|\bsuspect(ed)?\b|\babuse\b", re.IGNORECASE
        ),
    ),
)


def _strip_allowlisted_placeholders(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        token = match.group(0)
        return "" if token in PLACEHOLDER_ALLOWLIST else token

    return _PLACEHOLDER_TOKEN.sub(repl, text)


def check_gate(text: str) -> list[str]:
    """Returns the sorted list of gate-rule ids hit (empty => pass). Checked on NFKC-
    normalized, zero-width-stripped, allowlisted-placeholder-stripped text so `{amount}` etc.
    never trip G-DIGIT/G-CUR/G-PH themselves."""
    if not text:
        return []
    normalized = unicodedata.normalize("NFKC", text)
    normalized = re.sub(r"[\u200b-\u200f\u2060\ufeff]", "", normalized)
    body = _strip_allowlisted_placeholders(normalized)

    hits: set[str] = set()
    for gate_id, pattern in _GATE_PATTERNS:
        if pattern.search(body):
            hits.add(gate_id)

    for token in _PLACEHOLDER_TOKEN.findall(normalized):
        if token not in PLACEHOLDER_ALLOWLIST:
            hits.add("G-PH")
            break

    return sorted(hits)


__all__ = ["PLACEHOLDER_ALLOWLIST", "check_gate"]
