"""L3 integration: real Postgres (call_ledger/outbox), real FastAPI app, PayPal sandbox
calls stubbed with respx (never live sandbox per the dispatch prompt). Covers PA-C03/C04
(create_order + replay) and the capture_order pre-check/happy path at S1-08 scope.
"""

from __future__ import annotations

import uuid

import pytest
import respx
from httpx import Response

from .conftest import mint_ticket

PAYPAL_BASE = "https://api-m.sandbox.paypal.com"


def _token_route(mock):
    return mock.post(f"{PAYPAL_BASE}/v1/oauth2/token").mock(
        return_value=Response(200, json={"access_token": "tok", "expires_in": 32000})
    )


@pytest.mark.asyncio
async def test_missing_request_id_rejected(client, checkout_token):
    resp = await client.post(
        "/v1/orders",
        headers={"Authorization": f"Bearer {checkout_token}", "X-Authorization-Ticket": "t"},
        json={
            "mandate_id": "mdt_1",
            "proposal_hash": "sha256:abc",
            "internal_order_id": "ord_1",
            "amount_minor": 4999,
            "currency": "USD",
            "return_url": "http://localhost:3000/return",
            "cancel_url": "http://localhost:3000/cancel",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_order_then_replay_returns_same_order_no_second_paypal_call(
    client, checkout_token
):
    with respx.mock(assert_all_called=False) as mock:
        _token_route(mock)
        create_route = mock.post(f"{PAYPAL_BASE}/v2/checkout/orders").mock(
            return_value=Response(
                201,
                json={
                    "id": "ORDER123",
                    "status": "PAYER_ACTION_REQUIRED",
                    "links": [{"rel": "approve", "href": f"{PAYPAL_BASE}/approve"}],
                    "purchase_units": [
                        {
                            "custom_id": "mdt_1",
                            "invoice_id": "ord_1",
                            "amount": {"currency_code": "USD", "value": "49.99"},
                        }
                    ],
                },
            )
        )
        body = {
            "request_id": str(uuid.uuid4()),
            "mandate_id": "mdt_1",
            "proposal_hash": "sha256:abc",
            "internal_order_id": "ord_1",
            "amount_minor": 4999,
            "currency": "USD",
            "return_url": "http://localhost:3000/return",
            "cancel_url": "http://localhost:3000/cancel",
        }
        ticket = mint_ticket(
            "checkout",
            mandate_id="mdt_1",
            proposal_hash="sha256:abc",
            amount_minor=4999,
            currency="USD",
        )
        headers = {"Authorization": f"Bearer {checkout_token}", "X-Authorization-Ticket": ticket}

        resp1 = await client.post("/v1/orders", headers=headers, json=body)
        assert resp1.status_code == 201, resp1.text
        data1 = resp1.json()
        assert data1["ok"] is True
        assert data1["data"]["order_id"] == "ORDER123"
        assert data1["replayed"] is False

        resp2 = await client.post("/v1/orders", headers=headers, json=body)
        assert resp2.status_code in (200, 201)
        data2 = resp2.json()
        assert data2["replayed"] is True
        assert data2["data"]["order_id"] == "ORDER123"

        assert create_route.call_count == 1  # PayPal called exactly once despite the replay


@pytest.mark.asyncio
async def test_create_order_replay_with_different_body_rejected(client, checkout_token):
    with respx.mock(assert_all_called=False) as mock:
        _token_route(mock)
        mock.post(f"{PAYPAL_BASE}/v2/checkout/orders").mock(
            return_value=Response(
                201,
                json={
                    "id": "ORDER999",
                    "status": "PAYER_ACTION_REQUIRED",
                    "links": [],
                    "purchase_units": [
                        {
                            "custom_id": "mdt_1",
                            "invoice_id": "ord_1",
                            "amount": {"currency_code": "USD", "value": "10.00"},
                        }
                    ],
                },
            )
        )
        request_id = str(uuid.uuid4())
        base_body = {
            "request_id": request_id,
            "mandate_id": "mdt_1",
            "proposal_hash": "sha256:abc",
            "internal_order_id": "ord_1",
            "amount_minor": 1000,
            "currency": "USD",
            "return_url": "http://localhost:3000/return",
            "cancel_url": "http://localhost:3000/cancel",
        }
        ticket1 = mint_ticket(
            "checkout",
            mandate_id="mdt_1",
            proposal_hash="sha256:abc",
            amount_minor=1000,
            currency="USD",
        )
        resp1 = await client.post(
            "/v1/orders",
            headers={
                "Authorization": f"Bearer {checkout_token}",
                "X-Authorization-Ticket": ticket1,
            },
            json=base_body,
        )
        assert resp1.status_code == 201

        # Different amount -> a correctly-signed ticket for THAT amount (isolating the
        # ops-layer idempotency-key-reuse check below from ticket verification, which would
        # otherwise reject this with TICKET_INVALID first since the ticket binds amount_minor).
        different_body = {**base_body, "amount_minor": 2000}
        ticket2 = mint_ticket(
            "checkout",
            mandate_id="mdt_1",
            proposal_hash="sha256:abc",
            amount_minor=2000,
            currency="USD",
        )
        resp2 = await client.post(
            "/v1/orders",
            headers={
                "Authorization": f"Bearer {checkout_token}",
                "X-Authorization-Ticket": ticket2,
            },
            json=different_body,
        )
        assert resp2.status_code == 409
        assert resp2.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


@pytest.mark.asyncio
async def test_get_order_not_found_maps_to_404(client, checkout_token):
    with respx.mock(assert_all_called=False) as mock:
        _token_route(mock)
        mock.get(f"{PAYPAL_BASE}/v2/checkout/orders/MISSING").mock(
            return_value=Response(404, json={"name": "RESOURCE_NOT_FOUND"})
        )
        resp = await client.get(
            "/v1/orders/MISSING", headers={"Authorization": f"Bearer {checkout_token}"}
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_capture_order_pre_check_rejects_not_approved(client, checkout_token):
    with respx.mock(assert_all_called=False) as mock:
        _token_route(mock)
        mock.get(f"{PAYPAL_BASE}/v2/checkout/orders/ORDERABC").mock(
            return_value=Response(
                200,
                json={
                    "id": "ORDERABC",
                    "status": "PAYER_ACTION_REQUIRED",
                    "purchase_units": [{"custom_id": "mdt_1"}],
                },
            )
        )
        capture_route = mock.post(f"{PAYPAL_BASE}/v2/checkout/orders/ORDERABC/capture")
        ticket = mint_ticket(
            "checkout",
            mandate_id="mdt_1",
            proposal_hash="sha256:abc",
            amount_minor=4999,
            currency="USD",
        )
        resp = await client.post(
            "/v1/orders/ORDERABC/capture",
            headers={"Authorization": f"Bearer {checkout_token}", "X-Authorization-Ticket": ticket},
            json={
                "request_id": str(uuid.uuid4()),
                "mandate_id": "mdt_1",
                "proposal_hash": "sha256:abc",
                "amount_minor": 4999,
                "currency": "USD",
            },
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "ORDER_NOT_APPROVED"
        assert capture_route.call_count == 0  # pre-check must stop us before a real capture


@pytest.mark.asyncio
async def test_capture_order_happy_path(client, checkout_token):
    with respx.mock(assert_all_called=False) as mock:
        _token_route(mock)
        mock.get(f"{PAYPAL_BASE}/v2/checkout/orders/ORDEROK").mock(
            return_value=Response(
                200,
                json={
                    "id": "ORDEROK",
                    "status": "APPROVED",
                    "purchase_units": [{"custom_id": "mdt_1"}],
                },
            )
        )
        mock.post(f"{PAYPAL_BASE}/v2/checkout/orders/ORDEROK/capture").mock(
            return_value=Response(
                201,
                json={
                    "id": "ORDEROK",
                    "status": "COMPLETED",
                    # Real PayPal sandbox behavior (confirmed live): custom_id/invoice_id on
                    # a capture response come back on the CAPTURE object itself, not echoed
                    # on the wrapping purchase_unit -- the purchase_unit here deliberately
                    # omits them so this test fails if ops.capture_order regresses to reading
                    # capture_pu.get("custom_id") instead of capture.get("custom_id").
                    "purchase_units": [
                        {
                            "payments": {
                                "captures": [
                                    {
                                        "id": "CAP1",
                                        "status": "COMPLETED",
                                        "custom_id": "mdt_1",
                                        "invoice_id": "ord_1",
                                    }
                                ]
                            },
                        }
                    ],
                },
            )
        )
        ticket = mint_ticket(
            "checkout",
            mandate_id="mdt_1",
            proposal_hash="sha256:abc",
            amount_minor=4999,
            currency="USD",
        )
        resp = await client.post(
            "/v1/orders/ORDEROK/capture",
            headers={"Authorization": f"Bearer {checkout_token}", "X-Authorization-Ticket": ticket},
            json={
                "request_id": str(uuid.uuid4()),
                "mandate_id": "mdt_1",
                "proposal_hash": "sha256:abc",
                "amount_minor": 4999,
                "currency": "USD",
            },
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["data"]["capture_id"] == "CAP1"
        assert data["data"]["status"] == "COMPLETED"
        assert data["data"]["custom_id"] == "mdt_1"
        assert data["data"]["invoice_id"] == "ord_1"


@pytest.mark.asyncio
async def test_not_permitted_caller_rejected(client, tracking_token):
    resp = await client.post(
        "/v1/orders",
        headers={"Authorization": f"Bearer {tracking_token}", "X-Authorization-Ticket": "t"},
        json={
            "request_id": str(uuid.uuid4()),
            "mandate_id": "mdt_1",
            "proposal_hash": "sha256:abc",
            "internal_order_id": "ord_1",
            "amount_minor": 4999,
            "currency": "USD",
            "return_url": "http://localhost:3000/return",
            "cancel_url": "http://localhost:3000/cancel",
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_money_frozen_blocks_create_order(client, checkout_token, monkeypatch):
    monkeypatch.setenv("PS_PAYPALADAPTER_MONEY_ENABLED", "false")
    ticket = mint_ticket(
        "checkout",
        mandate_id="mdt_1",
        proposal_hash="sha256:abc",
        amount_minor=4999,
        currency="USD",
    )
    try:
        resp = await client.post(
            "/v1/orders",
            headers={"Authorization": f"Bearer {checkout_token}", "X-Authorization-Ticket": ticket},
            json={
                "request_id": str(uuid.uuid4()),
                "mandate_id": "mdt_1",
                "proposal_hash": "sha256:abc",
                "internal_order_id": "ord_1",
                "amount_minor": 4999,
                "currency": "USD",
                "return_url": "http://localhost:3000/return",
                "cancel_url": "http://localhost:3000/cancel",
            },
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "MONEY_FROZEN"
    finally:
        monkeypatch.setenv("PS_PAYPALADAPTER_MONEY_ENABLED", "true")
