"""Catalog pre-filter (build spec section 2): resolve buyer intent to a candidate SKU
subset via plain keyword/category matching -- NOT an LLM call. The /propose prompt is
grounded in this subset plus a few neighboring items, never the full catalog. This is
both a cost optimization (smaller prompt, fewer tokens against Groq's tight TPM cap)
and a reliability requirement (smaller, more relevant context measurably reduces
hallucination/schema-violation rates on extraction tasks per the reliability research
this build spec cites).

Pure function, no I/O, fully unit-testable.
"""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Minimum catalog subset size shown to the model even on a weak/empty match, so it can
# honestly say "no match" against real neighbors rather than inventing a substitute
# (llm-integration-spec.md section 5).
MIN_SUBSET_SIZE = 4
MAX_SUBSET_SIZE = 12


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def filter_catalog(
    catalog_items: list[dict],
    *,
    intent_text: str,
    allowed_merchant_ids: set[str] | None = None,
    max_subset_size: int = MAX_SUBSET_SIZE,
) -> list[dict]:
    """Rank `catalog_items` (each a dict with sku/title/category/merchant_id/
    description/price_minor) by keyword/category token overlap against `intent_text`,
    then return the top `max_subset_size`. Items whose merchant is not in
    `allowed_merchant_ids` (when given) are still eligible for the slice -- the
    prompt's job is to let the model see context and refuse; the deterministic
    validation layer (app/eval_validation.py), not this filter, is the real merchant
    gate. Ties broken by ascending price then SKU for determinism."""
    intent_tokens = _tokenize(intent_text)

    def score(item: dict) -> int:
        item_tokens = _tokenize(
            f"{item.get('title', '')} {item.get('category', '')} "
            f"{item.get('description', '')}"
        )
        return len(intent_tokens & item_tokens)

    scored = [(score(item), item) for item in catalog_items]
    scored.sort(
        key=lambda pair: (
            -pair[0],
            pair[1].get("price_minor") if pair[1].get("price_minor") is not None else 0,
            pair[1].get("sku", ""),
        )
    )

    subset = [item for _, item in scored[:max_subset_size]]

    pad_target = min(MIN_SUBSET_SIZE, max_subset_size, len(catalog_items))
    if len(subset) < pad_target:
        # Pad with neighboring items (by catalog order) so the model has enough context
        # to make an honest "no match" call instead of being starved of any context.
        seen_skus = {item["sku"] for item in subset}
        for item in catalog_items:
            if len(subset) >= pad_target:
                break
            if item["sku"] not in seen_skus:
                subset.append(item)
                seen_skus.add(item["sku"])

    return subset


__all__ = ["MAX_SUBSET_SIZE", "MIN_SUBSET_SIZE", "filter_catalog"]
