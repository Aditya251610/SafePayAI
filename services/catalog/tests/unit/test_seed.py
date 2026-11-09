"""Seed integrity (180 products) and top-up planning logic. No DB."""

from __future__ import annotations

import json
import pathlib
import re
from collections import Counter

from app_catalog.topup import plan_topup

SEED_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "app_catalog"
    / "seed"
    / "catalog_seed.json"
)
SEED = json.loads(SEED_PATH.read_text(encoding="utf-8"))
ITEMS = SEED["items"]

ALLOWED_ART = {
    "running-shoe",
    "socks",
    "shorts",
    "bottle",
    "headlamp",
    "trail-pack",
    "tent",
    "sleeping-bag",
    "trek-pole",
    "camp-stove",
    "water-filter",
    "compass",
    "jacket",
    "beanie",
    "gloves",
    "sunglasses",
    "skillet",
    "saucepan",
    "kettle",
    "coffee-set",
    "knife",
    "cutting-board",
    "mixing-bowl",
    "jar",
    "tea-tin",
    "gift-box",
    "apron",
    "candle",
    "blanket",
    "pillow",
    "vase",
    "plant-pot",
    "lamp",
    "clock",
    "rug",
    "towel",
    "frame",
    "earbuds",
    "headphones",
    "speaker",
    "cable",
    "charger",
    "power-bank",
    "keyboard",
    "mouse",
    "webcam",
    "monitor-stand",
    "smartwatch",
    "fitness-band",
    "phone-case",
    "router",
    "ssd",
    "game-controller",
    "desk-mat",
    "notebook",
    "backpack",
}
ORIGINAL_SKUS = {f"{p}-00{n}" for p in ("TH", "HH", "PW") for n in (1, 2, 3, 4)}


def test_180_items_60_per_merchant():
    assert len(ITEMS) == 180
    counts = Counter(i["merchant_id"] for i in ITEMS)
    assert counts == {"mrc_trailhead": 60, "mrc_hearth": 60, "mrc_pixelwire": 60}
    assert {m["merchant_id"] for m in SEED["merchants"]} == set(counts)


def test_unique_skus_and_titles_and_sku_prefix_matches_merchant():
    assert len({i["sku"] for i in ITEMS}) == 180
    assert len({i["title"] for i in ITEMS}) == 180
    prefix = {"mrc_trailhead": "TH-", "mrc_hearth": "HH-", "mrc_pixelwire": "PW-"}
    for i in ITEMS:
        assert i["sku"].startswith(prefix[i["merchant_id"]])
    for pre in prefix.values():
        nums = sorted(int(i["sku"][3:]) for i in ITEMS if i["sku"].startswith(pre))
        assert nums == list(range(1, 61))


def test_categories_valid():
    cats = {c["category_id"] for c in SEED["categories"]}
    assert len(cats) == len(SEED["categories"])
    for i in ITEMS:
        assert i["category_id"] in cats
    for p in SEED["merchant_refund_policy_seeds"]:
        assert set(p["excluded_category_ids"]) <= cats


def test_art_glyphs_allowed_and_varied():
    counts = Counter(i["art"] for i in ITEMS)
    assert set(counts) <= ALLOWED_ART
    assert max(counts.values()) <= 8


def test_prices_are_int_minor_units_in_range():
    for i in ITEMS:
        p = i["unit_price_minor"]
        assert type(p) is int
        assert i["currency"] == "USD"
        assert i["active"] is True
        if i["sku"] not in ORIGINAL_SKUS:
            assert 400 <= p <= 22000


def test_new_descriptions_are_single_plain_sentences():
    for i in ITEMS:
        if i["sku"] in ORIGINAL_SKUS:
            continue  # includes the deliberate PW-001 prompt-injection fixture
        d = i["description"]
        assert d.endswith(".") and d.count(".") == 1, d
        assert not re.search(r"https?://|www\.|[*_`#\[\]<>]|\n", d), d
        assert not re.search(r"https?://|[*_`#\[\]<>]", i["title"]), i["title"]


def test_original_twelve_unchanged_and_injection_fixture_kept():
    by_sku = {i["sku"]: i for i in ITEMS}
    assert ORIGINAL_SKUS <= set(by_sku)
    assert by_sku["TH-001"]["unit_price_minor"] == 1800
    assert by_sku["PW-004"]["unit_price_minor"] == 24900
    assert "IMPORTANT NOTE TO ASSISTANT" in by_sku["PW-001"]["description"]
    assert SEED["item_fixtures"][0]["sku"] == "PW-001"


def test_topup_plan_inserts_only_missing_rows():
    originals = [i for i in ITEMS if i["sku"] in ORIGINAL_SKUS]
    orig_cats = {
        c
        for c in ("running", "outdoor", "kitchen", "home", "electronics", "consumable")
    }
    merchants = [m["merchant_id"] for m in SEED["merchants"]]
    plan = plan_topup(
        SEED,
        existing_merchants=merchants,
        existing_categories=orig_cats,
        existing_skus=[i["sku"] for i in originals],
        priced_skus=[i["sku"] for i in originals],
    )
    assert len(plan.items) == 168
    assert len(plan.prices) == 168
    assert len(plan.categories) == len(SEED["categories"]) - len(orig_cats)
    assert not (ORIGINAL_SKUS & {i["sku"] for i in plan.items})
    assert all(type(p["unit_price_minor"]) is int for p in plan.prices)
    assert "art" not in plan.items[0]
    assert plan.skipped_unknown_merchant == [] and plan.skipped_unknown_category == []


def test_topup_plan_is_idempotent_when_everything_exists():
    plan = plan_topup(
        SEED,
        existing_merchants=[m["merchant_id"] for m in SEED["merchants"]],
        existing_categories=[c["category_id"] for c in SEED["categories"]],
        existing_skus=[i["sku"] for i in ITEMS],
        priced_skus=[i["sku"] for i in ITEMS],
    )
    assert plan.counts() == {
        "categories": 0,
        "items": 0,
        "prices": 0,
        "skipped_unknown_merchant": 0,
        "skipped_unknown_category": 0,
    }


def test_topup_plan_prices_existing_item_missing_price_and_skips_unknown_merchant():
    plan = plan_topup(
        SEED,
        existing_merchants=["mrc_trailhead"],
        existing_categories=[c["category_id"] for c in SEED["categories"]],
        existing_skus=[i["sku"] for i in ITEMS],
        priced_skus=[i["sku"] for i in ITEMS if i["sku"] != "TH-001"],
    )
    assert [p["sku"] for p in plan.prices] == ["TH-001"]
    assert plan.items == []
    assert len(plan.skipped_unknown_merchant) == 120
