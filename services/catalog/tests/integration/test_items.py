"""IT1-adjacent: items/merchants reads against the real, migrated DB via the runtime
role, plus the pagination cap (data-architecture.md section 13, limit <= 100)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


async def test_list_items_returns_all_twelve_seeded_items(client):
    resp = await client.get("/items", params={"limit": 100})
    assert resp.status_code == 200
    body = resp.json()
    assert body["catalog_version"] == 1
    assert len(body["items"]) == 12
    assert body["has_more"] is False
    skus = {item["sku"] for item in body["items"]}
    assert skus == {
        "TH-001",
        "TH-002",
        "TH-003",
        "TH-004",
        "HH-001",
        "HH-002",
        "HH-003",
        "HH-004",
        "PW-001",
        "PW-002",
        "PW-003",
        "PW-004",
    }


async def test_list_items_text_trust_and_label(client):
    resp = await client.get("/items", params={"limit": 100})
    body = resp.json()
    for item in body["items"]:
        assert item["text_trust"] == "untrusted"
        assert item["label"] == "SIMULATED"


async def test_list_items_filters_by_merchant(client):
    resp = await client.get("/items", params={"merchant_id": "mrc_trailhead"})
    body = resp.json()
    assert len(body["items"]) == 4
    assert all(item["merchant_id"] == "mrc_trailhead" for item in body["items"])


async def test_list_items_filters_by_category(client):
    resp = await client.get("/items", params={"category_id": "electronics"})
    body = resp.json()
    assert len(body["items"]) == 4
    assert all(item["category_id"] == "electronics" for item in body["items"])


async def test_pagination_respects_limit_and_offset(client):
    first_page = await client.get("/items", params={"limit": 5, "offset": 0})
    second_page = await client.get("/items", params={"limit": 5, "offset": 5})

    first_body = first_page.json()
    second_body = second_page.json()

    assert len(first_body["items"]) == 5
    assert first_body["has_more"] is True
    assert len(second_body["items"]) == 5
    assert second_body["has_more"] is True

    first_skus = [i["sku"] for i in first_body["items"]]
    second_skus = [i["sku"] for i in second_body["items"]]
    assert set(first_skus).isdisjoint(second_skus)


async def test_pagination_caps_limit_at_100(client):
    resp = await client.get("/items", params={"limit": 10_000})
    body = resp.json()
    assert resp.status_code == 200
    assert body["limit"] == 100
    # Only 12 items exist, so this also proves the cap didn't truncate real results.
    assert len(body["items"]) == 12
    assert body["has_more"] is False


async def test_get_item_by_sku(client):
    resp = await client.get("/items/TH-001")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sku"] == "TH-001"
    assert body["unit_price_minor"] == 1800
    assert body["currency"] == "USD"
    assert body["catalog_version"] == 1
    assert isinstance(body["unit_price_minor"], int)


async def test_get_unknown_item_returns_item_not_found(client):
    resp = await client.get("/items/DOES-NOT-EXIST")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "ITEM_NOT_FOUND"
    assert "request_id" in body


async def test_injection_fixture_served_verbatim_as_untrusted_plain_data(client):
    """F1/F2/F3 slice: PW-001's description contains the injection-style payload, is
    served byte-for-byte (catalog does not sanitize), and carries `text_trust:
    "untrusted"` with no fixture/injection marker key anywhere in the public response."""
    resp = await client.get("/items/PW-001")
    body = resp.json()
    assert resp.status_code == 200
    assert body["text_trust"] == "untrusted"
    assert "IMPORTANT NOTE TO ASSISTANT" in body["description"]
    assert "fixture" not in body
    assert "kind" not in body
    assert "expected_behavior" not in body


async def test_admin_fixtures_route_still_a_stub_not_reachable_via_items(client):
    """Confirms the fixture table's existence is never exposed through /items (F5
    slice, catalog's own scope) - /admin/fixtures itself stays a 501 stub this wave."""
    resp = await client.get("/admin/fixtures")
    assert resp.status_code == 501
