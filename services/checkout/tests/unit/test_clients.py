"""Fail-closed behavior of app/clients.py: catalog/mandate failures must raise
UpstreamError (never silently return an "allow"), per spec.md section 10.
"""

from __future__ import annotations

import httpx
import pytest

from app_checkout import clients
from app_checkout.settings import Settings


def _settings() -> Settings:
    return Settings(
        catalog_base_url="http://catalog.test",
        mandate_base_url="http://mandate.test",
        paypal_adapter_base_url="http://adapter.test",
    )


@pytest.mark.asyncio
async def test_resolve_prices_raises_on_connection_error(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    def fake_build_client(base_url, timeout=None):
        return httpx.AsyncClient(
            base_url=base_url, transport=httpx.MockTransport(handler)
        )

    monkeypatch.setattr(clients, "build_client", fake_build_client)
    with pytest.raises(clients.UpstreamError):
        await clients.resolve_prices(_settings(), "tok", [{"sku": "x", "qty": 1}])


@pytest.mark.asyncio
async def test_resolve_prices_raises_on_5xx(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "NOT_READY"})

    def fake_build_client(base_url, timeout=None):
        return httpx.AsyncClient(
            base_url=base_url, transport=httpx.MockTransport(handler)
        )

    monkeypatch.setattr(clients, "build_client", fake_build_client)
    with pytest.raises(clients.UpstreamError):
        await clients.resolve_prices(_settings(), "tok", [{"sku": "x", "qty": 1}])


@pytest.mark.asyncio
async def test_evaluate_mandate_raises_on_timeout(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    def fake_build_client(base_url, timeout=None):
        return httpx.AsyncClient(
            base_url=base_url, transport=httpx.MockTransport(handler)
        )

    monkeypatch.setattr(clients, "build_client", fake_build_client)
    with pytest.raises(clients.UpstreamError):
        await clients.evaluate_mandate(_settings(), "tok", "mandate-1", {"lines": []})


@pytest.mark.asyncio
async def test_create_order_timeout_is_not_definite(monkeypatch) -> None:
    """Timeout must map to CREATE_UNKNOWN (retryable with same request id), not a
    definite CREATE_FAILED - spec.md section 5 step 7 / section 10."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    def fake_build_client(base_url, timeout=None):
        return httpx.AsyncClient(
            base_url=base_url, transport=httpx.MockTransport(handler)
        )

    monkeypatch.setattr(clients, "build_client", fake_build_client)
    result = await clients.create_order(
        _settings(),
        "tok",
        idempotency_key="req-1",
        mandate_id="mandate-1",
        proposal_hash="hash-1",
        internal_order_id="order-1",
        amount_minor=100,
        currency="USD",
        return_url="http://x/return",
        cancel_url="http://x/cancel",
        ticket="ticket",
    )
    assert result.ok is False
    assert result.definite is False


@pytest.mark.asyncio
async def test_create_order_4xx_is_definite_failure(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"error": "VALIDATION_ERROR"})

    def fake_build_client(base_url, timeout=None):
        return httpx.AsyncClient(
            base_url=base_url, transport=httpx.MockTransport(handler)
        )

    monkeypatch.setattr(clients, "build_client", fake_build_client)
    result = await clients.create_order(
        _settings(),
        "tok",
        idempotency_key="req-1",
        mandate_id="mandate-1",
        proposal_hash="hash-1",
        internal_order_id="order-1",
        amount_minor=100,
        currency="USD",
        return_url="http://x/return",
        cancel_url="http://x/cancel",
        ticket="ticket",
    )
    assert result.ok is False
    assert result.definite is True
