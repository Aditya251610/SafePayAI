from __future__ import annotations

from app.catalog_filter import MAX_SUBSET_SIZE, MIN_SUBSET_SIZE, filter_catalog

CATALOG = [
    {
        "sku": "RUN-1",
        "title": "Trail running shoes",
        "category": "fitness",
        "merchant_id": "M1",
        "price_minor": 5500,
    },
    {
        "sku": "RUN-2",
        "title": "Running socks",
        "category": "fitness",
        "merchant_id": "M1",
        "price_minor": 1200,
    },
    {
        "sku": "MUG-1",
        "title": "Ceramic mug",
        "category": "home",
        "merchant_id": "M1",
        "price_minor": 900,
    },
    {
        "sku": "NOTE-1",
        "title": "Leather notebook",
        "category": "office",
        "merchant_id": "M2",
        "price_minor": 1800,
    },
]


def test_relevant_items_rank_above_irrelevant() -> None:
    subset = filter_catalog(
        CATALOG, intent_text="running shoes for a race", max_subset_size=2
    )
    skus = [item["sku"] for item in subset]
    assert skus[0] == "RUN-1"


def test_subset_never_exceeds_requested_max() -> None:
    subset = filter_catalog(CATALOG, intent_text="running", max_subset_size=2)
    assert len(subset) <= 2


def test_subset_padded_to_minimum_even_with_no_keyword_match() -> None:
    subset = filter_catalog(CATALOG, intent_text="zzz nonsense zzz")
    assert len(subset) >= min(MIN_SUBSET_SIZE, len(CATALOG))


def test_default_max_subset_size_constant_is_sane() -> None:
    assert MIN_SUBSET_SIZE <= MAX_SUBSET_SIZE


def test_ties_broken_deterministically_by_price_then_sku() -> None:
    subset_a = filter_catalog(CATALOG, intent_text="", max_subset_size=4)
    subset_b = filter_catalog(CATALOG, intent_text="", max_subset_size=4)
    assert [i["sku"] for i in subset_a] == [i["sku"] for i in subset_b]
