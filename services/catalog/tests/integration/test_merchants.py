"""GET /merchants, GET /merchants/{id}/refund-policy-seed, GET /categories,
GET /catalog/version - against the real migrated+seeded DB."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


async def test_list_merchants_returns_three_seeded_merchants(client):
    resp = await client.get("/merchants")
    assert resp.status_code == 200
    body = resp.json()
    merchant_ids = {m["merchant_id"] for m in body["merchants"]}
    assert merchant_ids == {"mrc_trailhead", "mrc_hearth", "mrc_pixelwire"}
    for merchant in body["merchants"]:
        assert merchant["settlement_alias"] == "SANDBOX_MERCHANT_PRIMARY"
        assert merchant["currency"] == "USD"


async def test_refund_policy_seed_for_known_merchant(client):
    resp = await client.get("/merchants/mrc_hearth/refund-policy-seed")
    assert resp.status_code == 200
    body = resp.json()
    assert body["merchant_id"] == "mrc_hearth"
    assert body["refund_cap_minor"] == 5000
    assert body["excluded_category_ids"] == ["consumable"]
    assert body["velocity_max_refunds"] == 2
    assert body["velocity_window_days"] == 30
    assert body["authoritative"] is False


async def test_refund_policy_seed_unknown_merchant_404(client):
    resp = await client.get("/merchants/mrc_does_not_exist/refund-policy-seed")
    assert resp.status_code == 404
    assert resp.json()["error"] == "MERCHANT_NOT_FOUND"


async def test_list_categories_returns_six_seeded_categories(client):
    resp = await client.get("/categories")
    assert resp.status_code == 200
    body = resp.json()
    category_ids = {c["category_id"] for c in body["categories"]}
    assert category_ids == {
        "running",
        "outdoor",
        "kitchen",
        "home",
        "electronics",
        "consumable",
    }


async def test_catalog_version_matches_seed(client):
    resp = await client.get("/catalog/version")
    assert resp.status_code == 200
    body = resp.json()
    assert body["catalog_version"] == 1
    assert body["item_count"] == 12
    assert body["merchant_count"] == 3
    assert len(body["seed_hash"]) == 64  # sha256 hex digest


async def test_responses_carry_data_label_and_request_id_headers(client):
    resp = await client.get("/merchants")
    assert resp.headers["x-data-label"] == "simulated-seed"
    assert "x-request-id" in resp.headers


async def test_unauthenticated_caller_rejected(client):
    # Temporarily drop the dependency override to exercise the real auth path.
    from app.deps import verify_internal_jwt
    from app.main import app

    app.dependency_overrides.pop(verify_internal_jwt, None)
    resp = await client.get("/merchants")
    assert resp.status_code == 401
    assert resp.json()["error"] == "UNAUTHENTICATED"
