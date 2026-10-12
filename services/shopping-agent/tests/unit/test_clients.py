"""Catalog/mandate client failures must fail closed to the documented exceptions
(spec.md section 11: CATALOG_UNAVAILABLE / MANDATE_UNAVAILABLE / MANDATE_NOT_FOUND)."""

from __future__ import annotations

import httpx
import pytest

from app import clients


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


@pytest.mark.asyncio
async def test_fetch_catalog_items_returns_items_on_success(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"catalog_version": 1, "items": [{"sku": "A"}]})

    _patched_client(monkeypatch, handler)
    items = await clients.fetch_catalog_items(
        base_url="http://catalog.test", bearer_token="t"
    )
    assert items == [{"sku": "A"}]


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
