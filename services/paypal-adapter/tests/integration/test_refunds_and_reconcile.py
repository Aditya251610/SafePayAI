"""L3 integration: real Postgres (call_ledger/refund_ledger/outbox), real FastAPI app,
PayPal sandbox calls stubbed with respx (never live sandbox). Covers refund_capture's
own-ledger amount derivation / idempotency / 409-ambiguity handling, get_refund's
ledger-first-then-live-PayPal fallback, reconcile's read-only replay lookup, and the
no-`/v1`-prefix compat routes that match resolution's already-merged Wave 5B client exactly
(services/resolution/app/clients.py refund_capture/get_refund/reconcile_refund).
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


async def _capture_order(client, checkout_token, mock, *, order_id: str, capture_id: str) -> None:
    """Seeds a DONE_OK capture_order row in our own call_ledger (amount_minor=4999, USD,
    paypal_object_id=capture_id) the same way checkout would in the real flow -- refund's
    own-ledger amount derivation (CLAUDE.md: never trust the caller's amount without
    checking our own ledger) reads this row, not a live PayPal get_capture call."""
    mock.get(f"{PAYPAL_BASE}/v2/checkout/orders/{order_id}").mock(
        return_value=Response(
            200,
            json={"id": order_id, "status": "APPROVED", "purchase_units": [{"custom_id": "mdt_1"}]},
        )
    )
    mock.post(f"{PAYPAL_BASE}/v2/checkout/orders/{order_id}/capture").mock(
        return_value=Response(
            201,
            json={
                "id": order_id,
                "status": "COMPLETED",
                "purchase_units": [
                    {
                        "custom_id": "mdt_1",
                        "invoice_id": "ord_1",
                        "payments": {"captures": [{"id": capture_id, "status": "COMPLETED"}]},
                    }
                ],
            },
        )
    )
    capture_ticket = mint_ticket(
        "checkout",
        mandate_id="mdt_1",
        proposal_hash="sha256:abc",
        amount_minor=4999,
        currency="USD",
    )
    resp = await client.post(
        f"/v1/orders/{order_id}/capture",
        headers={
            "Authorization": f"Bearer {checkout_token}",
            "X-Authorization-Ticket": capture_ticket,
        },
        json={
            "request_id": str(uuid.uuid4()),
            "mandate_id": "mdt_1",
            "proposal_hash": "sha256:abc",
            "amount_minor": 4999,
            "currency": "USD",
        },
    )
    assert resp.status_code == 201, resp.text


def _refund_ticket(amount_minor: int, currency: str = "USD") -> str:
    """Matches the mandate_id/proposal_hash every test in this file uses for its capture
    (see _capture_order above) -- resolution's own refund_capture call always sends these
    two fields now (services/resolution/app/usecases/execute_refund.py), so the ticket must
    bind the same values or real verification correctly rejects it."""
    return mint_ticket(
        "resolution",
        mandate_id="mdt_1",
        proposal_hash="sha256:abc",
        amount_minor=amount_minor,
        currency=currency,
    )


@pytest.mark.asyncio
async def test_refund_capture_happy_path(client, checkout_token, resolution_token):
    with respx.mock(assert_all_called=False) as mock:
        _token_route(mock)
        await _capture_order(client, checkout_token, mock, order_id="ORDER_R1", capture_id="CAP_R1")

        refund_route = mock.post(f"{PAYPAL_BASE}/v2/payments/captures/CAP_R1/refund").mock(
            return_value=Response(
                201,
                json={
                    "id": "REFUND_R1",
                    "status": "COMPLETED",
                    "links": [{"rel": "up", "href": f"{PAYPAL_BASE}/v2/payments/captures/CAP_R1"}],
                },
            )
        )
        resp = await client.post(
            "/v1/captures/CAP_R1/refund",
            headers={"Authorization": f"Bearer {resolution_token}"},
            json={
                "request_id": str(uuid.uuid4()),
                "invoice_id": "ord_1",
                "amount_minor": 1000,
                "currency": "USD",
                "mandate_id": "mdt_1",
                "proposal_hash": "sha256:abc",
                "ticket": _refund_ticket(1000),
            },
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["refund_id"] == "REFUND_R1"
        assert data["data"]["status"] == "COMPLETED"
        assert refund_route.call_count == 1


@pytest.mark.asyncio
async def test_refund_capture_replay_same_body_no_second_paypal_call(
    client, checkout_token, resolution_token
):
    with respx.mock(assert_all_called=False) as mock:
        _token_route(mock)
        await _capture_order(client, checkout_token, mock, order_id="ORDER_R2", capture_id="CAP_R2")
        refund_route = mock.post(f"{PAYPAL_BASE}/v2/payments/captures/CAP_R2/refund").mock(
            return_value=Response(201, json={"id": "REFUND_R2", "status": "COMPLETED", "links": []})
        )
        request_id = str(uuid.uuid4())
        body = {
            "request_id": request_id,
            "invoice_id": "ord_1",
            "amount_minor": 1000,
            "currency": "USD",
            "mandate_id": "mdt_1",
            "proposal_hash": "sha256:abc",
            "ticket": _refund_ticket(1000),
        }
        headers = {"Authorization": f"Bearer {resolution_token}"}

        resp1 = await client.post("/v1/captures/CAP_R2/refund", headers=headers, json=body)
        assert resp1.status_code == 201
        assert resp1.json()["replayed"] is False

        resp2 = await client.post("/v1/captures/CAP_R2/refund", headers=headers, json=body)
        assert resp2.status_code in (200, 201)
        assert resp2.json()["replayed"] is True
        assert resp2.json()["data"]["refund_id"] == "REFUND_R2"
        assert refund_route.call_count == 1


@pytest.mark.asyncio
async def test_refund_capture_replay_with_mutated_amount_rejected(
    client, checkout_token, resolution_token
):
    """CLAUDE.md: PayPal itself would return the ORIGINAL refund on a Request-Id replay even
    with a different amount -- we must reject this ourselves, before ever calling PayPal
    again, using our own ledger's body-hash equality check."""
    with respx.mock(assert_all_called=False) as mock:
        _token_route(mock)
        await _capture_order(client, checkout_token, mock, order_id="ORDER_R3", capture_id="CAP_R3")
        refund_route = mock.post(f"{PAYPAL_BASE}/v2/payments/captures/CAP_R3/refund").mock(
            return_value=Response(201, json={"id": "REFUND_R3", "status": "COMPLETED", "links": []})
        )
        request_id = str(uuid.uuid4())
        headers = {"Authorization": f"Bearer {resolution_token}"}
        base_body = {
            "request_id": request_id,
            "invoice_id": "ord_1",
            "amount_minor": 1000,
            "currency": "USD",
            "mandate_id": "mdt_1",
            "proposal_hash": "sha256:abc",
            "ticket": _refund_ticket(1000),
        }
        resp1 = await client.post("/v1/captures/CAP_R3/refund", headers=headers, json=base_body)
        assert resp1.status_code == 201

        # A correctly-signed ticket for the mutated amount, isolating the ops-layer
        # idempotency-key-reuse check from ticket verification (same reasoning as
        # test_create_order_replay_with_different_body_rejected).
        mutated = {**base_body, "amount_minor": 2000, "ticket": _refund_ticket(2000)}
        resp2 = await client.post("/v1/captures/CAP_R3/refund", headers=headers, json=mutated)
        assert resp2.status_code == 409
        assert resp2.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
        assert refund_route.call_count == 1  # second call never reached PayPal


@pytest.mark.asyncio
async def test_refund_capture_amount_exceeds_refundable_remaining_rejected(
    client, checkout_token, resolution_token
):
    with respx.mock(assert_all_called=False) as mock:
        _token_route(mock)
        await _capture_order(client, checkout_token, mock, order_id="ORDER_R4", capture_id="CAP_R4")
        refund_route = mock.post(f"{PAYPAL_BASE}/v2/payments/captures/CAP_R4/refund")
        resp = await client.post(
            "/v1/captures/CAP_R4/refund",
            headers={"Authorization": f"Bearer {resolution_token}"},
            json={
                "request_id": str(uuid.uuid4()),
                "invoice_id": "ord_1",
                "amount_minor": 5000,  # captured amount was 4999
                "currency": "USD",
                "mandate_id": "mdt_1",
                "proposal_hash": "sha256:abc",
                "ticket": _refund_ticket(5000),
            },
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "REFUND_AMOUNT_EXCEEDED"
        assert refund_route.call_count == 0  # rejected before ever calling PayPal


@pytest.mark.asyncio
async def test_refund_capture_unknown_capture_rejected_not_found(client, resolution_token):
    with respx.mock(assert_all_called=False) as mock:
        _token_route(mock)
        resp = await client.post(
            "/v1/captures/NEVER_CAPTURED/refund",
            headers={"Authorization": f"Bearer {resolution_token}"},
            json={
                "request_id": str(uuid.uuid4()),
                "amount_minor": 100,
                "currency": "USD",
                "mandate_id": "mdt_1",
                "proposal_hash": "sha256:abc",
                "ticket": _refund_ticket(100),
            },
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_refund_capture_checkout_not_permitted(client, checkout_token):
    """Dispatch prompt: resolution may refund, checkout may not."""
    resp = await client.post(
        "/v1/captures/CAP_X/refund",
        headers={"Authorization": f"Bearer {checkout_token}"},
        json={
            "request_id": str(uuid.uuid4()),
            "amount_minor": 100,
            "currency": "USD",
            "ticket": "opaque",
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_refund_capture_409_from_paypal_is_in_progress_not_rejected(
    client, checkout_token, resolution_token
):
    """A 409 from PayPal means UNKNOWN/ambiguous, not FAILED -- route to reconcile, never
    treat as a normal rejection and never auto-retry."""
    with respx.mock(assert_all_called=False) as mock:
        _token_route(mock)
        await _capture_order(client, checkout_token, mock, order_id="ORDER_R5", capture_id="CAP_R5")
        mock.post(f"{PAYPAL_BASE}/v2/payments/captures/CAP_R5/refund").mock(
            return_value=Response(409, json={"name": "CONCURRENT_REQUEST"})
        )
        resp = await client.post(
            "/v1/captures/CAP_R5/refund",
            headers={"Authorization": f"Bearer {resolution_token}"},
            json={
                "request_id": str(uuid.uuid4()),
                "amount_minor": 1000,
                "currency": "USD",
                "mandate_id": "mdt_1",
                "proposal_hash": "sha256:abc",
                "ticket": _refund_ticket(1000),
            },
        )
        assert resp.status_code == 202
        assert resp.json()["status"] == "IN_PROGRESS"


@pytest.mark.asyncio
async def test_get_refund_fast_path_from_own_ledger(client, checkout_token, resolution_token):
    with respx.mock(assert_all_called=False) as mock:
        _token_route(mock)
        await _capture_order(client, checkout_token, mock, order_id="ORDER_R6", capture_id="CAP_R6")
        mock.post(f"{PAYPAL_BASE}/v2/payments/captures/CAP_R6/refund").mock(
            return_value=Response(201, json={"id": "REFUND_R6", "status": "COMPLETED", "links": []})
        )
        await client.post(
            "/v1/captures/CAP_R6/refund",
            headers={"Authorization": f"Bearer {resolution_token}"},
            json={
                "request_id": str(uuid.uuid4()),
                "amount_minor": 1000,
                "currency": "USD",
                "mandate_id": "mdt_1",
                "proposal_hash": "sha256:abc",
                "ticket": _refund_ticket(1000),
            },
        )

        get_refund_route = mock.get(f"{PAYPAL_BASE}/v2/payments/refunds/REFUND_R6")
        resp = await client.get(
            "/v1/refunds/REFUND_R6", headers={"Authorization": f"Bearer {resolution_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["refund_id"] == "REFUND_R6"
        assert data["status"] == "COMPLETED"
        assert data["amount_minor"] == 1000
        assert get_refund_route.call_count == 0  # served from our own ledger, no live PayPal call


@pytest.mark.asyncio
async def test_get_refund_falls_back_to_live_paypal_when_not_in_our_ledger(
    client, resolution_token
):
    with respx.mock(assert_all_called=False) as mock:
        _token_route(mock)
        mock.get(f"{PAYPAL_BASE}/v2/payments/refunds/EXTERNAL_REFUND").mock(
            return_value=Response(
                200,
                json={
                    "id": "EXTERNAL_REFUND",
                    "status": "PENDING",
                    "amount": {"currency_code": "USD", "value": "5.00"},
                    "links": [{"rel": "up", "href": f"{PAYPAL_BASE}/v2/payments/captures/CAP_EXT"}],
                },
            )
        )
        resp = await client.get(
            "/v1/refunds/EXTERNAL_REFUND", headers={"Authorization": f"Bearer {resolution_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["refund_id"] == "EXTERNAL_REFUND"
        assert data["amount_minor"] == 500
        assert data["capture_id"] == "CAP_EXT"


@pytest.mark.asyncio
async def test_reconcile_unknown_request_id_is_404(client, resolution_token):
    resp = await client.post(
        f"/v1/reconcile/{uuid.uuid4()}", headers={"Authorization": f"Bearer {resolution_token}"}
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_reconcile_replays_done_ok_without_calling_paypal_again(
    client, checkout_token, resolution_token
):
    with respx.mock(assert_all_called=False) as mock:
        _token_route(mock)
        await _capture_order(client, checkout_token, mock, order_id="ORDER_R7", capture_id="CAP_R7")
        refund_route = mock.post(f"{PAYPAL_BASE}/v2/payments/captures/CAP_R7/refund").mock(
            return_value=Response(201, json={"id": "REFUND_R7", "status": "COMPLETED", "links": []})
        )
        request_id = str(uuid.uuid4())
        resp1 = await client.post(
            "/v1/captures/CAP_R7/refund",
            headers={"Authorization": f"Bearer {resolution_token}"},
            json={
                "request_id": request_id,
                "amount_minor": 1000,
                "currency": "USD",
                "mandate_id": "mdt_1",
                "proposal_hash": "sha256:abc",
                "ticket": _refund_ticket(1000),
            },
        )
        assert resp1.status_code == 201

        resp2 = await client.post(
            f"/v1/reconcile/{request_id}",
            headers={"Authorization": f"Bearer {resolution_token}"},
        )
        assert resp2.status_code == 200
        body = resp2.json()
        assert body["ok"] is True
        assert body["replayed"] is True
        assert body["data"]["refund_id"] == "REFUND_R7"
        assert refund_route.call_count == 1  # reconcile never re-calls PayPal


@pytest.mark.asyncio
async def test_compat_routes_without_v1_prefix_match_resolutions_client(
    client, checkout_token, resolution_token
):
    """Exact HTTP contract resolution's Wave 5B client already calls (services/resolution/
    app/clients.py refund_capture/get_refund/reconcile_refund): no `/v1` prefix."""
    with respx.mock(assert_all_called=False) as mock:
        _token_route(mock)
        await _capture_order(client, checkout_token, mock, order_id="ORDER_R8", capture_id="CAP_R8")
        mock.post(f"{PAYPAL_BASE}/v2/payments/captures/CAP_R8/refund").mock(
            return_value=Response(201, json={"id": "REFUND_R8", "status": "COMPLETED", "links": []})
        )
        request_id = str(uuid.uuid4())
        headers = {
            "PayPal-Request-Id": request_id,
            "Authorization": f"Bearer {resolution_token}",
        }
        refund_resp = await client.post(
            "/captures/CAP_R8/refund",
            headers=headers,
            json={
                "request_id": request_id,
                "invoice_id": "ord_1",
                "amount_minor": 1000,
                "currency": "USD",
                "mandate_id": "mdt_1",
                "proposal_hash": "sha256:abc",
                "ticket": _refund_ticket(1000),
            },
        )
        assert refund_resp.status_code == 201, refund_resp.text

        get_resp = await client.get(
            "/refunds/REFUND_R8", headers={"Authorization": f"Bearer {resolution_token}"}
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["data"]["refund_id"] == "REFUND_R8"

        reconcile_resp = await client.post(
            f"/reconcile/{request_id}", headers={"Authorization": f"Bearer {resolution_token}"}
        )
        assert reconcile_resp.status_code == 200
        assert reconcile_resp.json()["replayed"] is True


@pytest.mark.asyncio
async def test_mcp_refund_capture_wired_to_real_ops(client, checkout_token, resolution_token):
    """MCP tools/call for refund_capture goes through the same app.ops.refund_capture path
    as the REST route -- one code path for money."""
    with respx.mock(assert_all_called=False) as mock:
        _token_route(mock)
        await _capture_order(client, checkout_token, mock, order_id="ORDER_R9", capture_id="CAP_R9")
        mock.post(f"{PAYPAL_BASE}/v2/payments/captures/CAP_R9/refund").mock(
            return_value=Response(201, json={"id": "REFUND_R9", "status": "COMPLETED", "links": []})
        )
        resp = await client.post(
            "/mcp",
            headers={"Authorization": f"Bearer {resolution_token}"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "refund_capture",
                    "arguments": {
                        "capture_id": "CAP_R9",
                        "request_id": str(uuid.uuid4()),
                        "amount_minor": 1000,
                        "currency": "USD",
                        "mandate_id": "mdt_1",
                        "proposal_hash": "sha256:abc",
                        "ticket": _refund_ticket(1000),
                    },
                },
            },
        )
        assert resp.status_code == 200
        result = resp.json()["result"]
        assert result["isError"] is False
        assert result["structuredContent"]["data"]["refund_id"] == "REFUND_R9"
