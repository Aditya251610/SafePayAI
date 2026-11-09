"""Pure planning logic for scripts/topup_seed.py (no DB, no I/O).

Migration 0002 runs once, so a deployed DB keeps the 12-item seed even after the seed
JSON grows. The top-up script diffs the seed against what exists and inserts only the
missing rows for the CURRENT catalog version; it never updates, deletes or bumps the
version. Extra seed keys (e.g. `art`) are ignored: there is no DB column for them.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class TopupPlan:
    categories: list[dict] = field(default_factory=list)
    items: list[dict] = field(default_factory=list)
    prices: list[dict] = field(default_factory=list)
    skipped_unknown_merchant: list[str] = field(default_factory=list)
    skipped_unknown_category: list[str] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {
            "categories": len(self.categories),
            "items": len(self.items),
            "prices": len(self.prices),
            "skipped_unknown_merchant": len(self.skipped_unknown_merchant),
            "skipped_unknown_category": len(self.skipped_unknown_category),
        }


def plan_topup(
    seed: dict,
    *,
    existing_merchants: Iterable[str],
    existing_categories: Iterable[str],
    existing_skus: Iterable[str],
    priced_skus: Iterable[str],
) -> TopupPlan:
    """Diff the seed against existing keys. `priced_skus` = skus that already have an
    item_prices row at the current catalog version."""
    merchants = set(existing_merchants)
    have_cats = set(existing_categories)
    have_skus = set(existing_skus)
    have_prices = set(priced_skus)

    new_cats = [
        {"category_id": c["category_id"], "display_name": c["display_name"]}
        for c in seed["categories"]
        if c["category_id"] not in have_cats
    ]
    known_cats = have_cats | {c["category_id"] for c in new_cats}

    items: list[dict] = []
    prices: list[dict] = []
    bad_merchant: list[str] = []
    bad_cat: list[str] = []
    for it in seed["items"]:
        sku = it["sku"]
        if it["merchant_id"] not in merchants:
            bad_merchant.append(sku)
            continue
        if it["category_id"] not in known_cats:
            bad_cat.append(sku)
            continue
        if sku not in have_skus:
            items.append(
                {
                    "sku": sku,
                    "merchant_id": it["merchant_id"],
                    "category_id": it["category_id"],
                    "title": it["title"],
                    "description": it["description"],
                    "active": it["active"],
                }
            )
        if sku not in have_prices:
            prices.append(
                {
                    "sku": sku,
                    "unit_price_minor": int(it["unit_price_minor"]),
                    "currency": it["currency"],
                }
            )
    return TopupPlan(new_cats, items, prices, bad_merchant, bad_cat)
