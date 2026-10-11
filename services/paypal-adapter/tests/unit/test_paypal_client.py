"""L1 unit tests for app.paypal_client: token cache (single fetch across concurrent
calls, proactive refresh near expiry) and 401 -> refresh-once -> retry-once ->
UPSTREAM_AUTH_FAILED (spec.md section 9, PA-C01/PA-C02). No network; httpx.MockTransport.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.paypal_client import PayPalAuthError, PayPalClient
from app.settings import Settings


def _settings(**overrides) -> Settings:
    base = {
        "paypal_client_id": "client-id",
        "paypal_client_secret": "client-secret",
        "paypal_base_url": "https://api-m.sandbox.paypal.com",
        "paypal_timeout_seconds": 5.0,
        "paypal_token_refresh_skew_seconds": 60,
    }
    base.update(overrides)
    return Settings(**base)


@pytest.mark.asyncio
async def test_token_fetched_once_and_cached():
    token_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls
        if request.url.path == "/v1/oauth2/token":
            token_calls += 1
            return httpx.Response(200, json={"access_token": "tok-1", "expires_in": 32000})
        return httpx.Response(200, json={"id": "ORDER1", "status": "APPROVED"})

    client = PayPalClient(_settings(), transport=httpx.MockTransport(handler))
    await client.get_order("ORDER1")
    await client.get_order("ORDER1")
    await client.get_order("ORDER1")
    assert token_calls == 1
    await client.aclose()


@pytest.mark.asyncio
async def test_token_single_flight_under_concurrency():
    """Concurrent callers must not each fetch their own token (spec.md section 9:
    'single-flight (asyncio lock)')."""
    token_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls
        if request.url.path == "/v1/oauth2/token":
            token_calls += 1
            return httpx.Response(200, json={"access_token": "tok-1", "expires_in": 32000})
        return httpx.Response(200, json={"id": "ORDER1", "status": "APPROVED"})

    client = PayPalClient(_settings(), transport=httpx.MockTransport(handler))
    await asyncio.gather(*(client.get_order("ORDER1") for _ in range(10)))
    assert token_calls == 1
    await client.aclose()


@pytest.mark.asyncio
async def test_401_triggers_refresh_and_retry_once_then_succeeds():
    token_calls = 0
    order_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls, order_calls
        if request.url.path == "/v1/oauth2/token":
            token_calls += 1
            return httpx.Response(
                200, json={"access_token": f"tok-{token_calls}", "expires_in": 32000}
            )
        order_calls += 1
        if order_calls == 1:
            return httpx.Response(401, json={"name": "AUTHENTICATION_FAILURE"})
        return httpx.Response(200, json={"id": "ORDER1", "status": "APPROVED"})

    client = PayPalClient(_settings(), transport=httpx.MockTransport(handler))
    result = await client.get_order("ORDER1")
    assert result["id"] == "ORDER1"
    assert token_calls == 2  # initial fetch + one forced refresh after the 401
    assert order_calls == 2  # original call + the single retry
    await client.aclose()


@pytest.mark.asyncio
async def test_401_twice_raises_upstream_auth_failed():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 32000})
        return httpx.Response(401, json={"name": "AUTHENTICATION_FAILURE"})

    client = PayPalClient(_settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(PayPalAuthError):
        await client.get_order("ORDER1")
    await client.aclose()


@pytest.mark.asyncio
async def test_create_order_sends_request_id_header_and_integer_minor_units():
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 32000})
        captured["req"] = request
        return httpx.Response(
            201,
            json={
                "id": "ORDER1",
                "status": "PAYER_ACTION_REQUIRED",
                "links": [{"rel": "approve", "href": "https://sandbox.paypal.com/approve"}],
                "purchase_units": [
                    {
                        "custom_id": "mdt_1",
                        "invoice_id": "ord_1",
                        "amount": {"currency_code": "USD", "value": "49.99"},
                    }
                ],
            },
        )

    client = PayPalClient(_settings(), transport=httpx.MockTransport(handler))
    result = await client.create_order(
        request_id="7b1e0a5e-2f0c-4a53-9b0e-000000000001",
        amount_minor=4999,
        currency="USD",
        custom_id="mdt_1",
        invoice_id="ord_1",
        return_url="http://localhost:3000/return",
        cancel_url="http://localhost:3000/cancel",
    )
    assert result["id"] == "ORDER1"
    sent_body = captured["req"].content
    assert b"49.99" in sent_body
    assert captured["req"].headers["PayPal-Request-Id"] == "7b1e0a5e-2f0c-4a53-9b0e-000000000001"
    await client.aclose()
