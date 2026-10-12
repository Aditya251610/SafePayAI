"""Static fallback content for /draft (regex-gate reject, kill switch, or any LLM failure)
and /brief (code-built, always-available base). Reviewed once, stored in repo - never
generated at runtime (spec.md section 7).

Scope note: spec.md section 7 describes a template keyed on the full (category, outcome,
audience) cross product. This ships one reviewed template per category (the part that
actually varies the wording) with an outcome-aware opening line, which covers the same
money-safety property (allowlisted placeholders only, never a real figure) with a much
smaller reviewed surface. Flagged as a scope reduction from the full cross product, not a
gap in the gate itself.
"""

from __future__ import annotations

_OUTCOME_OPENERS = {
    "REFUND_OFFER_INSIDE_TERMS": "We are preparing a refund offer for",
    "APPROVAL_REQUESTED": "Your request is pending approval for",
    "UNDER_REVIEW": "We are reviewing",
    "INFO_REQUEST": "We need a bit more information about",
}

_CATEGORY_BODY = {
    "LATE": "it appears delayed",
    "LOST": "it may be lost in transit",
    "DAMAGED": "the reported damage",
    "WRONG_ITEM": "the reported item mismatch",
    "NOT_AS_DESCRIBED": "the reported description mismatch",
    "OTHER": "your case",
}


def static_draft(
    category: str, outcome: str, order_ref: str
) -> tuple[str, str, list[str]]:
    """Returns (subject, body, placeholders_used). Body contains ONLY the allowlisted
    placeholder tokens, never a real value - the caller (resolution) fills them server-side."""
    opener = _OUTCOME_OPENERS.get(outcome, "We are reviewing")
    detail = _CATEGORY_BODY.get(category, "your case")
    subject = "Update on your order"
    body = (
        f"{opener} order {{order_ref}} - {detail}. We will follow up by {{date}}."
        if outcome != "INFO_REQUEST"
        else f"{opener} order {{order_ref}} - {detail}. A team member will reach out."
    )
    _ = order_ref  # the order_ref VALUE is never interpolated here; {order_ref} stays a placeholder
    return (
        subject,
        body,
        ["{order_ref}", "{date}"] if outcome != "INFO_REQUEST" else ["{order_ref}"],
    )


def static_brief_summary(*, category: str | None, state: str) -> str:
    if category:
        return f"Buyer reports {category}. Case state: {state}. Deterministic summary (LLM unavailable or disabled)."
    return f"Case state: {state}. Deterministic summary (LLM unavailable or disabled)."


__all__ = ["static_brief_summary", "static_draft"]
