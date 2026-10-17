from __future__ import annotations

from app_shopping_agent.form_fallback import match_form_intent, match_free_text_fallback

CATALOG = [
    {
        "sku": "MUG-1",
        "title": "Ceramic mug",
        "category": "home",
        "merchant_id": "M1",
        "price_minor": 900,
    },
    {
        "sku": "MUG-2",
        "title": "Travel mug",
        "category": "home",
        "merchant_id": "M1",
        "price_minor": 1500,
    },
    {
        "sku": "RUN-1",
        "title": "Running socks",
        "category": "fitness",
        "merchant_id": "M1",
        "price_minor": 1200,
    },
    {
        "sku": "EXP-1",
        "title": "Luxury item",
        "category": "home",
        "merchant_id": "M3",
        "price_minor": 99999,
    },
]


def test_form_match_filters_by_category_budget_and_allowlist() -> None:
    matches = match_form_intent(
        CATALOG,
        category="home",
        max_budget_minor=2000,
        quantity=1,
        allowed_merchant_ids={"M1", "M2"},
    )
    assert len(matches) == 1
    assert matches[0].sku in {"MUG-1", "MUG-2"}


def test_form_match_never_returns_non_allowlisted_merchant() -> None:
    matches = match_form_intent(
        CATALOG,
        category="home",
        max_budget_minor=1_000_000,
        quantity=1,
        allowed_merchant_ids={"M1"},
    )
    assert all(m.sku != "EXP-1" for m in matches)


def test_form_match_empty_when_nothing_fits_budget() -> None:
    matches = match_form_intent(
        CATALOG,
        category="home",
        max_budget_minor=100,
        quantity=1,
        allowed_merchant_ids={"M1"},
    )
    assert matches == []


def test_keyword_overlap_breaks_ties_toward_matching_title() -> None:
    matches = match_form_intent(
        CATALOG,
        category="home",
        max_budget_minor=2000,
        quantity=1,
        allowed_merchant_ids={"M1"},
        keywords="travel",
    )
    assert matches[0].sku == "MUG-2"


def test_free_text_fallback_never_matches_non_allowlisted_merchant() -> None:
    matches = match_free_text_fallback(
        CATALOG, intent_text="luxury item please", allowed_merchant_ids={"M1"}
    )
    assert all(m.sku != "EXP-1" for m in matches)


def test_free_text_fallback_no_match_returns_empty() -> None:
    matches = match_free_text_fallback(
        CATALOG, intent_text="zzz totally unrelated zzz", allowed_merchant_ids={"M1"}
    )
    assert matches == []
