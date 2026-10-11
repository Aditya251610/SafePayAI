"""Shared request-body builders for integration tests."""

from __future__ import annotations


def sample_terms(**overrides) -> dict:
    terms = {
        "currency": "USD",
        "max_total_minor": 6000,
        "max_qty_per_line": 2,
        "merchant_allowlist": [{"merchant_id": "shop-a", "display_name": "Shop A"}],
        "intent_text": "birthday gift for a runner",
        "expires_at": "2026-11-01T12:00:00Z",
        "protection": {"kinds_covered": ["LATE", "LOST"], "max_refund_minor": 5000, "deliver_by_days": 7},
    }
    terms.update(overrides)
    return terms


async def preview_and_sign(client, buyer_token: str, idempotency_key: str, **term_overrides) -> dict:
    headers = {"Authorization": f"Bearer {buyer_token}"}
    preview_resp = await client.post(
        "/mandates/preview", json={"terms": sample_terms(**term_overrides)}, headers=headers
    )
    assert preview_resp.status_code == 200, preview_resp.text
    preview = preview_resp.json()

    sign_resp = await client.post(
        "/mandates",
        json={
            "terms": sample_terms(**term_overrides),
            "screen_text_hash": preview["screen_text_hash"],
            "nonce": preview["nonce"],
        },
        headers={**headers, "Idempotency-Key": idempotency_key},
    )
    assert sign_resp.status_code == 201, sign_resp.text
    return sign_resp.json()


def sample_cart(**overrides) -> dict:
    cart = {
        "currency": "USD",
        "lines": [
            {
                "sku": "sku-1",
                "qty": 1,
                "unit_minor": 2500,
                "line_minor": 2500,
                "merchant_id": "shop-a",
                "sku_known": True,
                "stated_unit_minor": 2500,
            }
        ],
        "total_minor": 2500,
    }
    cart.update(overrides)
    return cart
