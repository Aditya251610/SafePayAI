"""Catalog/mandate client failures must fail closed to the documented exceptions
(spec.md section 11: CATALOG_UNAVAILABLE / MANDATE_UNAVAILABLE / MANDATE_NOT_FOUND)."""

from __future__ import annotations

import httpx
import pytest

from app_shopping_agent import clients


def _patched_client(monkeypatch, handler) -> None:
    def fake_build_client(base_url, timeout=None):
        return httpx.AsyncClient(
            base_url=base_url, transport=httpx.MockTransport(handler)
        )

    monkeypatch.setattr(clients, "build_client", fake_build_client)


@pytest.mark.asyncio
async def test_fetch_catalog_items_raises_on_connection_error(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    _patched_client(monkeypatch, handler)
    with pytest.raises(clients.CatalogUnavailableError):
        await clients.fetch_catalog_items(
            base_url="http://catalog.test", bearer_token="t"
        )


@pytest.mark.asyncio
async def test_fetch_catalog_items_raises_on_5xx(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "NOT_READY"})

    _patched_client(monkeypatch, handler)
    with pytest.raises(clients.CatalogUnavailableError):
        await clients.fetch_catalog_items(
            base_url="http://catalog.test", bearer_token="t"
        )


def _real_catalog_item(**overrides) -> dict:
    """catalog's real Item schema (services/catalog/app/schemas/items.py) -- NOT the
    {category, price_minor} shape the agent's own internals use. Mocking the wrong shape
    here is exactly how the real category_id/unit_price_minor vs category/price_minor
    mismatch went uncaught."""
    item = {
        "sku": "A",
        "merchant_id": "shop-a",
        "category_id": "cat-1",
        "title": "Widget",
        "description": "a widget",
        "unit_price_minor": 2500,
        "currency": "USD",
        "active": True,
    }
    item.update(overrides)
    return item


@pytest.mark.asyncio
async def test_fetch_catalog_items_returns_items_on_success(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "catalog_version": 1,
                "items": [_real_catalog_item()],
                "limit": 100,
                "offset": 0,
                "has_more": False,
            },
        )

    _patched_client(monkeypatch, handler)
    items = await clients.fetch_catalog_items(
        base_url="http://catalog.test", bearer_token="t"
    )
    assert len(items) == 1
    assert items[0]["category"] == "cat-1"
    assert items[0]["price_minor"] == 2500
    assert "category_id" not in items[0]
    assert "unit_price_minor" not in items[0]


@pytest.mark.asyncio
async def test_fetch_catalog_items_drops_inactive_items(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "catalog_version": 1,
                "items": [
                    _real_catalog_item(sku="active-1", active=True),
                    _real_catalog_item(sku="inactive-1", active=False),
                ],
                "limit": 100,
                "offset": 0,
                "has_more": False,
            },
        )

    _patched_client(monkeypatch, handler)
    items = await clients.fetch_catalog_items(
        base_url="http://catalog.test", bearer_token="t"
    )
    assert [i["sku"] for i in items] == ["active-1"]


@pytest.mark.asyncio
async def test_fetch_catalog_items_follows_has_more_pagination(monkeypatch) -> None:
    seen_offsets: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params["offset"])
        seen_offsets.append(offset)
        if offset == 0:
            return httpx.Response(
                200,
                json={
                    "catalog_version": 1,
                    "items": [_real_catalog_item(sku="a")],
                    "limit": 100,
                    "offset": 0,
                    "has_more": True,
                },
            )
        return httpx.Response(
            200,
            json={
                "catalog_version": 1,
                "items": [_real_catalog_item(sku="b")],
                "limit": 100,
                "offset": offset,
                "has_more": False,
            },
        )

    _patched_client(monkeypatch, handler)
    items = await clients.fetch_catalog_items(
        base_url="http://catalog.test", bearer_token="t"
    )
    assert [i["sku"] for i in items] == ["a", "b"]
    assert seen_offsets == [0, 100]


@pytest.mark.asyncio
async def test_fetch_mandate_summary_raises_not_found_on_404(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "MANDATE_NOT_FOUND"})

    _patched_client(monkeypatch, handler)
    with pytest.raises(clients.MandateNotFoundError):
        await clients.fetch_mandate_summary(
            base_url="http://mandate.test", mandate_id="m1", bearer_token="t"
        )


@pytest.mark.asyncio
async def test_fetch_mandate_summary_raises_unavailable_on_timeout(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    _patched_client(monkeypatch, handler)
    with pytest.raises(clients.MandateUnavailableError):
        await clients.fetch_mandate_summary(
            base_url="http://mandate.test", mandate_id="m1", bearer_token="t"
        )


@pytest.mark.asyncio
async def test_fetch_mandate_summary_returns_body_on_success(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"allowed_merchant_ids": ["M1"], "max_total_minor": 5000}
        )

    _patched_client(monkeypatch, handler)
    body = await clients.fetch_mandate_summary(
        base_url="http://mandate.test", mandate_id="m1", bearer_token="t"
    )
    assert body["max_total_minor"] == 5000
