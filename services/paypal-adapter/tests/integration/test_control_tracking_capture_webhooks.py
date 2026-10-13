"""L3 integration: real Postgres (control_flags), real FastAPI app, PayPal sandbox calls
stubbed with respx (never live sandbox). Covers the 7 endpoints that were 501 stubs before
this wave: GET /v1/captures/{id}, GET/POST /v1/control/*, POST /v1/orders/{id}/track,
GET /v1/orders/{id}/trackers/{id}, POST /v1/webhooks/paypal (disabled-by-default path only --
full signature verification is not live-testable in this suite, no real PayPal webhook
transmission is reachable here).
"""

from __future__ import annotations

import uuid

import pytest
import respx
from httpx import Response

PAYPAL_BASE = "https://api-m.sandbox.paypal.com"


def _token_route(mock):
    return mock.post(f"{PAYPAL_BASE}/v1/oauth2/token").mock(
        return_value=Response(200, json={"access_token": "tok", "expires_in": 32000})
    )


# -- control -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_control_status_unauthenticated_rejected(client):
    resp = await client.get("/v1/control/status")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_control_status_reports_seeded_row(client, checkout_token):
    resp = await client.get(
        "/v1/control/status", headers={"Authorization": f"Bearer {checkout_token}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["seeded"] is True
    # conftest's pg_env fixture unfreezes the seeded row for this whole test session.
    assert body["frozen"] is False


@pytest.mark.asyncio
async def test_freeze_then_unfreeze_round_trips(client, checkout_token):
    headers = {"Authorization": f"Bearer {checkout_token}"}
    frozen_resp = await client.post("/v1/control/freeze", headers=headers)
    assert frozen_resp.status_code == 200
    assert frozen_resp.json()["frozen"] is True

    status_resp = await client.get("/v1/control/status", headers=headers)
    assert status_resp.json()["frozen"] is True

    unfrozen_resp = await client.post("/v1/control/unfreeze", headers=headers)
    assert unfrozen_resp.status_code == 200
    assert unfrozen_resp.json()["frozen"] is False


@pytest.mark.asyncio
async def test_freeze_blocks_capture_order_money_op(client, checkout_token):
    """The DB frozen flag alone (static env var still says money_enabled=true) must block
    a money op -- the OR-fail-closed logic added this wave."""
    headers = {"Authorization": f"Bearer {checkout_token}"}
    await client.post("/v1/control/freeze", headers=headers)
    try:
        with respx.mock(assert_all_called=False) as mock:
            _token_route(mock)
            resp = await client.post(
                "/v1/orders/ORDER_FREEZE/capture",
                headers={**headers, "X-Authorization-Ticket": "t"},
                json={
                    "request_id": str(uuid.uuid4()),
                    "mandate_id": "mdt_1",
                    "proposal_hash": "sha256:abc",
                    "amount_minor": 4999,
                    "currency": "USD",
                },
            )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "MONEY_FROZEN"
    finally:
        await client.post("/v1/control/unfreeze", headers=headers)


# -- get_capture ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_capture_happy_path(client, checkout_token):
    with respx.mock(assert_all_called=False) as mock:
        _token_route(mock)
        mock.get(f"{PAYPAL_BASE}/v2/payments/captures/CAP_G1").mock(
            return_value=Response(
                200,
                json={
                    "id": "CAP_G1",
                    "status": "COMPLETED",
                    "amount": {"currency_code": "USD", "value": "15.00"},
                    "invoice_id": "ord_1",
                    "custom_id": "mdt_1",
                    "final_capture": True,
                },
            )
        )
        resp = await client.get(
            "/v1/captures/CAP_G1", headers={"Authorization": f"Bearer {checkout_token}"}
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["capture_id"] == "CAP_G1"
    assert body["data"]["amount_minor"] == 1500


@pytest.mark.asyncio
async def test_get_capture_not_found(client, checkout_token):
    with respx.mock(assert_all_called=False) as mock:
        _token_route(mock)
        mock.get(f"{PAYPAL_BASE}/v2/payments/captures/MISSING").mock(
            return_value=Response(404, json={"name": "RESOURCE_NOT_FOUND"})
        )
        resp = await client.get(
            "/v1/captures/MISSING", headers={"Authorization": f"Bearer {checkout_token}"}
        )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_capture_wrong_caller_rejected(client, shopping_agent_token):
    """get_capture's allowlist is checkout/tracking/resolution only -- an LLM-holding caller
    (shopping-agent, ADR-010) must be denied regardless of what PayPal would have returned."""
    resp = await client.get(
        "/v1/captures/CAP_X", headers={"Authorization": f"Bearer {shopping_agent_token}"}
    )
    assert resp.status_code == 403


# -- tracking ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_tracking_happy_path(client, tracking_token):
    with respx.mock(assert_all_called=False) as mock:
        _token_route(mock)
        mock.post(f"{PAYPAL_BASE}/v2/checkout/orders/ORDER_T1/track").mock(
            return_value=Response(201, json={"trackers": [{"status": "SHIPPED"}]})
        )
        resp = await client.post(
            "/v1/orders/ORDER_T1/track",
            headers={"Authorization": f"Bearer {tracking_token}"},
            json={
                "request_id": str(uuid.uuid4()),
                "capture_id": "CAP_T1",
                "tracking_number": "TRACK1",
                "carrier_name_other": "Demo Carrier (simulated)",
                "notify_payer": False,
            },
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["tracker_id"] == "CAP_T1-TRACK1"


@pytest.mark.asyncio
async def test_add_tracking_wrong_caller_rejected(client, resolution_token):
    resp = await client.post(
        "/v1/orders/ORDER_T2/track",
        headers={"Authorization": f"Bearer {resolution_token}"},
        json={
            "request_id": str(uuid.uuid4()),
            "capture_id": "CAP_T2",
            "tracking_number": "TRACK2",
            "carrier_name_other": "Demo Carrier",
            "notify_payer": False,
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_tracking_happy_path(client, tracking_token):
    with respx.mock(assert_all_called=False) as mock:
        _token_route(mock)
        mock.get(f"{PAYPAL_BASE}/v2/checkout/orders/ORDER_T3/trackers/CAP_T3-TRACK3").mock(
            return_value=Response(200, json={"id": "CAP_T3-TRACK3", "status": "SHIPPED"})
        )
        resp = await client.get(
            "/v1/orders/ORDER_T3/trackers/CAP_T3-TRACK3",
            headers={"Authorization": f"Bearer {tracking_token}"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"]["verified"] is False
    assert body["data"]["carrier_status"] is None
    assert body["data"]["paypal_status"] == "SHIPPED"


# -- webhooks (disabled by default; no live signature verification path is testable here) --


@pytest.mark.asyncio
async def test_webhook_disabled_by_default(client):
    resp = await client.post("/v1/webhooks/paypal", json={"event_type": "X"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["status"] == "DISABLED"
