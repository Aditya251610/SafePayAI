"""POST /prices/resolve - price-integrity (PI-series) and validation (U-series) tests
per catalog/test-plan.md, scoped to what the Wave 5 task asked for explicitly: golden
price table, unknown SKU, qty bounds, and "no float anywhere"."""

from __future__ import annotations

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration

# Golden price table, verbatim from spec.md section 2 / catalog_seed.json.
GOLDEN_PRICES = {
    "TH-001": 1800,
    "TH-002": 2400,
    "TH-003": 2900,
    "TH-004": 8900,
    "HH-001": 3400,
    "HH-002": 4500,
    "HH-003": 2200,
    "HH-004": 5900,
    "PW-001": 1299,
    "PW-002": 5900,
    "PW-003": 7900,
    "PW-004": 24900,
}


async def test_golden_price_table_every_seeded_sku(client):
    for sku, expected_price in GOLDEN_PRICES.items():
        resp = await client.post(
            "/prices/resolve", json={"lines": [{"sku": sku, "qty": 1}]}
        )
        assert resp.status_code == 200, f"{sku}: {resp.text}"
        body = resp.json()
        line = body["lines"][0]
        assert line["unit_price_minor"] == expected_price
        assert line["line_total_minor"] == expected_price
        assert body["total_minor"] == expected_price
        assert body["currency"] == "USD"
        assert line["price_mismatch"] is False


async def test_golden_price_table_qty_multiplies_exactly(client):
    resp = await client.post(
        "/prices/resolve", json={"lines": [{"sku": "TH-001", "qty": 3}]}
    )
    body = resp.json()
    assert body["lines"][0]["line_total_minor"] == 1800 * 3 == 5400
    assert body["total_minor"] == 5400


async def test_mixed_merchant_cart_totals_sum_correctly(client):
    resp = await client.post(
        "/prices/resolve",
        json={"lines": [{"sku": "TH-001", "qty": 2}, {"sku": "HH-002", "qty": 1}]},
    )
    body = resp.json()
    assert resp.status_code == 200
    assert body["total_minor"] == (1800 * 2) + (4500 * 1) == 8100
    assert set(body["merchant_ids"]) == {"mrc_trailhead", "mrc_hearth"}
    assert body["price_mismatch_any"] is False


async def test_unknown_sku_rejected(client):
    resp = await client.post(
        "/prices/resolve", json={"lines": [{"sku": "XX-999", "qty": 1}]}
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "UNKNOWN_SKU"
    assert body["details"]["skus"] == ["XX-999"]


async def test_unknown_sku_full_list_reported_never_partial(client):
    resp = await client.post(
        "/prices/resolve",
        json={
            "lines": [
                {"sku": "TH-001", "qty": 1},
                {"sku": "ZZ-1", "qty": 1},
                {"sku": "ZZ-2", "qty": 1},
            ]
        },
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "UNKNOWN_SKU"
    assert set(body["details"]["skus"]) == {"ZZ-1", "ZZ-2"}


async def test_qty_at_max_line_qty_passes(client):
    # PS_CATALOG_MAX_LINE_QTY default is 10 (.env.example / settings.py).
    resp = await client.post(
        "/prices/resolve", json={"lines": [{"sku": "TH-001", "qty": 10}]}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["lines"][0]["line_total_minor"] == 1800 * 10


async def test_qty_over_max_line_qty_rejected(client):
    resp = await client.post(
        "/prices/resolve", json={"lines": [{"sku": "TH-001", "qty": 11}]}
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "INVALID_QUANTITY"
    assert body["details"]["max_line_qty"] == 10


async def test_qty_zero_rejected(client):
    resp = await client.post(
        "/prices/resolve", json={"lines": [{"sku": "TH-001", "qty": 0}]}
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "INVALID_QUANTITY"


async def test_qty_negative_rejected(client):
    resp = await client.post(
        "/prices/resolve", json={"lines": [{"sku": "TH-001", "qty": -1}]}
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "INVALID_QUANTITY"


async def test_empty_cart_rejected(client):
    resp = await client.post("/prices/resolve", json={"lines": []})
    assert resp.status_code == 422
    assert resp.json()["error"] == "EMPTY_CART"


async def test_duplicate_sku_rejected(client):
    resp = await client.post(
        "/prices/resolve",
        json={"lines": [{"sku": "TH-001", "qty": 1}, {"sku": "TH-001", "qty": 2}]},
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "DUPLICATE_SKU_LINE"


async def test_currency_mismatch_rejected(client):
    resp = await client.post(
        "/prices/resolve",
        json={"lines": [{"sku": "TH-001", "qty": 1}], "currency": "EUR"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "CURRENCY_MISMATCH"


async def test_unknown_catalog_version_rejected(client):
    resp = await client.post(
        "/prices/resolve",
        json={"lines": [{"sku": "TH-001", "qty": 1}], "catalog_version": 999},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "CATALOG_VERSION_UNKNOWN"


async def test_extra_body_field_rejected(client):
    """PI5: a top-level `total`/`amount`/`price` injected into the body is rejected at
    the schema level, nothing resolved, no partial pricing."""
    resp = await client.post(
        "/prices/resolve",
        json={"lines": [{"sku": "TH-001", "qty": 1}], "total": 1},
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "VALIDATION_ERROR"


async def test_extra_line_field_rejected(client):
    resp = await client.post(
        "/prices/resolve",
        json={"lines": [{"sku": "TH-001", "qty": 1, "price": 1}]},
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("agent_price", [4000, 4500, 5000, 0, -1, 10**9])
async def test_agent_stated_price_never_changes_the_sum(client, agent_price):
    """PI1-PI3/PI6: whatever the caller claims the price is, the DB price always wins
    and the total is always DB-sourced."""
    resp = await client.post(
        "/prices/resolve",
        json={
            "lines": [
                {"sku": "HH-002", "qty": 1, "agent_stated_price_minor": agent_price}
            ]
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    line = body["lines"][0]
    assert line["unit_price_minor"] == 4500
    assert line["line_total_minor"] == 4500
    assert body["total_minor"] == 4500
    assert line["price_mismatch"] == (agent_price != 4500)
    assert body["price_mismatch_any"] == (agent_price != 4500)


async def test_agent_stated_price_matching_db_has_no_mismatch(client):
    resp = await client.post(
        "/prices/resolve",
        json={"lines": [{"sku": "HH-002", "qty": 1, "agent_stated_price_minor": 4500}]},
    )
    body = resp.json()
    assert body["lines"][0]["price_mismatch"] is False
    assert body["price_mismatch_any"] is False


async def test_no_agent_stated_price_no_mismatch_attempted(client):
    resp = await client.post(
        "/prices/resolve", json={"lines": [{"sku": "HH-002", "qty": 1}]}
    )
    body = resp.json()
    assert body["lines"][0]["price_mismatch"] is False


async def test_too_many_lines_rejected(client):
    # PS_CATALOG_MAX_LINES default is 20 (.env.example / settings.py). Line-count is
    # checked before any DB lookup (spec.md section 5 step 2), so made-up SKUs are
    # fine here - the point is this bound rejects before UNKNOWN_SKU would even apply.
    too_many_lines = [{"sku": f"FAKE-{i}", "qty": 1} for i in range(21)]
    resp = await client.post("/prices/resolve", json={"lines": too_many_lines})
    assert resp.status_code == 422
    assert resp.json()["error"] == "VALIDATION_ERROR"
    assert resp.json()["details"]["max_lines"] == 20


async def test_max_lines_at_the_limit_passes_schema_gate(client):
    """At exactly PS_CATALOG_MAX_LINES, the line-count gate itself must not reject -
    confirms the bound is `> max_lines`, not `>= max_lines`."""
    at_limit = [{"sku": f"FAKE-{i}", "qty": 1} for i in range(20)]
    resp = await client.post("/prices/resolve", json={"lines": at_limit})
    # Expect UNKNOWN_SKU (the made-up SKUs), never VALIDATION_ERROR for line count.
    assert resp.status_code == 422
    assert resp.json()["error"] == "UNKNOWN_SKU"


async def test_inactive_item_rejected_in_latest_version(client, admin_conn):
    await admin_conn.execute(
        text("UPDATE catalog.items SET active = false WHERE sku = 'TH-002'")
    )
    await admin_conn.commit()
    try:
        resp = await client.post(
            "/prices/resolve", json={"lines": [{"sku": "TH-002", "qty": 1}]}
        )
        assert resp.status_code == 422
        assert resp.json()["error"] == "ITEM_INACTIVE"
        assert resp.json()["details"]["skus"] == ["TH-002"]
    finally:
        await admin_conn.execute(
            text("UPDATE catalog.items SET active = true WHERE sku = 'TH-002'")
        )
        await admin_conn.commit()


async def test_response_has_no_float_in_money_fields(client):
    resp = await client.post(
        "/prices/resolve",
        json={"lines": [{"sku": "TH-001", "qty": 2}, {"sku": "PW-004", "qty": 1}]},
    )
    body = resp.json()
    assert isinstance(body["total_minor"], int)
    for line in body["lines"]:
        assert isinstance(line["unit_price_minor"], int)
        assert isinstance(line["line_total_minor"], int)
        assert isinstance(line["qty"], int)
