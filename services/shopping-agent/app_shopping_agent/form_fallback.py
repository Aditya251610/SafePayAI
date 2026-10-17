"""Deterministic, non-LLM fallback cart matcher (spec.md section 7). Used for
`mode="form"` requests, the kill-switch/breaker/quota `AI_PAUSED` path, and as the
"form fallback first, NO_PROPOSAL only if form also cannot answer" rule (spec.md
conflict C6) when the live LLM path fails or returns an unsafe/invalid result.

Pure function, no I/O, fully unit-testable and eval-able alongside the LLM path
(spec.md section 7: "Pure function; unit-testable and eval-able").
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FormMatch:
    sku: str
    quantity: int
    display_title: str


def match_form_intent(
    catalog_items: list[dict],
    *,
    category: str,
    max_budget_minor: int,
    quantity: int,
    allowed_merchant_ids: set[str],
    merchant_id: str | None = None,
    keywords: str | None = None,
) -> list[FormMatch]:
    """spec.md section 7 algorithm: filter by category + allowlisted merchant (+
    optional explicit merchant_id, itself required to already be in the allowlist),
    drop items whose reference price x quantity exceeds max_budget_minor, rank by
    keyword token overlap then ascending price then SKU, return the single top line."""
    candidates = [
        item
        for item in catalog_items
        if item.get("category") == category
        and item.get("merchant_id") in allowed_merchant_ids
        and (merchant_id is None or item.get("merchant_id") == merchant_id)
        and item.get("price_minor") is not None
        and item["price_minor"] * quantity <= max_budget_minor
    ]
    if not candidates:
        return []

    keyword_tokens = set((keywords or "").lower().split())

    def keyword_overlap(item: dict) -> int:
        title_tokens = set(item.get("title", "").lower().split())
        return len(keyword_tokens & title_tokens)

    candidates.sort(
        key=lambda item: (-keyword_overlap(item), item["price_minor"], item["sku"])
    )
    top = candidates[0]
    return [FormMatch(sku=top["sku"], quantity=quantity, display_title=top["title"])]


def match_free_text_fallback(
    catalog_items: list[dict],
    *,
    intent_text: str,
    allowed_merchant_ids: set[str],
) -> list[FormMatch]:
    """spec.md section 7, last paragraph: free-text intent submitted while fallback is
    active is tokenised against titles/categories (never sent to an LLM); no match ->
    caller returns NO_MATCH with the "pick items manually" prompt."""
    from app_shopping_agent.catalog_filter import filter_catalog

    allowlisted = [
        item
        for item in catalog_items
        if item.get("merchant_id") in allowed_merchant_ids
    ]
    if not allowlisted:
        return []
    ranked = filter_catalog(allowlisted, intent_text=intent_text, max_subset_size=1)
    if not ranked:
        return []
    top = ranked[0]
    intent_tokens = set(intent_text.lower().split())
    title_tokens = set(top.get("title", "").lower().split())
    category_tokens = {top.get("category", "").lower()}
    if not (intent_tokens & title_tokens) and not (intent_tokens & category_tokens):
        return []
    return [FormMatch(sku=top["sku"], quantity=1, display_title=top["title"])]


__all__ = ["FormMatch", "match_form_intent", "match_free_text_fallback"]
