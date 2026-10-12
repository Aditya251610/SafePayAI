"""Integration tests for POST /orders/{id}/capture, POST /orders/return,
POST /orders/cancel, GET /orders/{id}/receipt (sprint-plan S2-01/S2-02). catalog/mandate/
paypal-adapter calls are monkeypatched at the app.clients function level -- no real
network -- per this service's existing pattern (test_carts_and_orders.py); these tests
exercise checkout's own DB/transaction logic (R4 ordering, revoke-at-capture-time check,
never-recapture-after-timeout, idempotent return/capture) for real.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from app import clients


def _priced_response(total_minor: int = 2000) -> dict:
    return {
        "catalog_version": 1,
        "currency": "USD",
        "lines": [
            {
                "sku": "sku-1",
                "merchant_id": "merchant-1",
                "category_id": "cat-1",
                "qty": 1,
                "unit_price_minor": total_minor,
                "line_total_minor": total_minor,
                "settlement_alias": "merchant-1-alias",
                "price_mismatch": False,
                "latest_unit_price_minor": None,
            }
        ],
        "merchant_ids": ["merchant-1"],
        "total_minor": total_minor,
        "price_mismatch_any": False,
    }


def _allow_eval_response(
    mandate_id: str = "22222222-2222-2222-2222-222222222222",
) -> dict:
    return {
        "decision": "ALLOW",
        "hard_blocks": [],
        "advisory_flags": [],
        "mandate": {
            "mandate_id": mandate_id,
            "mandate_hash": "hash-1",
            "status": "active",
            "remaining_minor": 10000,
            "policy_version": "v1",
        },
        "evaluated_at": "2026-01-01T00:00:00Z",
    }


def _active_mandate(mandate_id: str = "22222222-2222-2222-2222-222222222222") -> dict:
    return {
        "mandate_id": mandate_id,
        "status": "active",
        "remaining_minor": 8000,
        "protection": {
            "kinds_covered": ["late", "lost"],
            "max_refund_minor": 5000,
            "deliver_by_days": 14,
        },
    }


def _extract_state(url: str) -> str:
    return parse_qs(urlparse(url).query)["state"][0]


async def _create_and_confirm(
    client, monkeypatch, *, idem: str, total_minor: int = 2000
) -> tuple[dict, str, str]:
    """Returns (confirm_body, return_state, cancel_state)."""

    async def _resolve(*a, **k):
        return _priced_response(total_minor)

    async def _evaluate(*a, **k):
        return _allow_eval_response()

    captured_urls: dict[str, str] = {}

    async def _create_order(settings, token, *, return_url, cancel_url, **k):
        captured_urls["return_url"] = return_url
        captured_urls["cancel_url"] = cancel_url
        return clients.AdapterResult(
            True,
            True,
            {
                "paypal_order_id": "PAY-" + idem,
                "approve_url": "https://paypal.test/approve",
            },
            "created",
        )

    monkeypatch.setattr(clients, "resolve_prices", _resolve)
    monkeypatch.setattr(clients, "evaluate_mandate", _evaluate)
    monkeypatch.setattr(clients, "create_order", _create_order)

    create_resp = await client.post(
        "/carts",
        json={
            "mandate_id": "22222222-2222-2222-2222-222222222222",
            "lines": [{"sku": "sku-1", "qty": 1}],
        },
    )
    cart_body = create_resp.json()

    confirm_resp = await client.post(
        f"/carts/{cart_body['cart_id']}/confirm",
        json={"proposal_hash": cart_body["proposal_hash"]},
        headers={"Idempotency-Key": idem},
    )
    assert confirm_resp.status_code == 201, confirm_resp.text
    body = confirm_resp.json()
    return (
        body,
        _extract_state(captured_urls["return_url"]),
        _extract_state(captured_urls["cancel_url"]),
    )


@pytest.mark.asyncio
async def test_capture_endpoint_success_builds_receipt(client, monkeypatch) -> None:
    body, _return_state, _cancel_state = await _create_and_confirm(
        client, monkeypatch, idem="cap-1"
    )
    order_id = body["order_id"]
    paypal_order_id = "PAY-cap-1"

    async def _get_mandate(*a, **k):
        return _active_mandate()

    async def _get_order(*a, **k):
        return clients.AdapterResult(
            True,
            True,
            {
                "order_id": paypal_order_id,
                "status": "APPROVED",
                "custom_id": "22222222-2222-2222-2222-222222222222",
                "invoice_id": order_id,
                "amount_minor": 2000,
                "currency": "USD",
                "capture_ids": [],
            },
            "ok",
        )

    async def _capture_order(*a, **k):
        return clients.AdapterResult(
            True,
            True,
            {
                "order_id": paypal_order_id,
                "status": "COMPLETED",
                "capture_id": "CAP-1",
                "capture_status": "COMPLETED",
                "custom_id": "22222222-2222-2222-2222-222222222222",
                "invoice_id": order_id,
                "amount_minor": 2000,
                "currency": "USD",
            },
            "captured",
        )

    monkeypatch.setattr(clients, "get_mandate", _get_mandate)
    monkeypatch.setattr(clients, "get_order", _get_order)
    monkeypatch.setattr(clients, "capture_order", _capture_order)

    resp = await client.post(
        f"/orders/{order_id}/capture", json={}, headers={"Idempotency-Key": "capture-1"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "CAPTURED"

    receipt_resp = await client.get(f"/orders/{order_id}/receipt")
    assert receipt_resp.status_code == 200, receipt_resp.text
    receipt = receipt_resp.json()
    assert receipt["amount_minor"] == 2000
    assert receipt["amount_major"] == "20.00"
    assert "Merchant-funded via PayPal refund" in receipt["disclosures"]
    text = str(receipt).lower()
    for forbidden in (
        "paypal-backed",
        "legally binding",
        "non-repudiable",
        "fraud-proof",
    ):
        assert forbidden not in text


@pytest.mark.asyncio
async def test_capture_timeout_then_reconcile_never_recaptures(
    client, monkeypatch
) -> None:
    """S2-01: a capture timeout must move the order to CAPTURE_UNKNOWN, and the next
    attempt must reconcile via get_order (adopting COMPLETED) rather than calling
    capture_order a second time."""
    body, _return_state, _cancel_state = await _create_and_confirm(
        client, monkeypatch, idem="cap-2"
    )
    order_id = body["order_id"]
    paypal_order_id = "PAY-cap-2"

    async def _get_mandate(*a, **k):
        return _active_mandate()

    async def _get_order_approved(*a, **k):
        return clients.AdapterResult(
            True,
            True,
            {
                "order_id": paypal_order_id,
                "status": "APPROVED",
                "custom_id": "22222222-2222-2222-2222-222222222222",
                "invoice_id": order_id,
                "amount_minor": 2000,
                "currency": "USD",
                "capture_ids": [],
            },
            "ok",
        )

    capture_calls = {"count": 0}

    async def _capture_order_timeout(*a, **k):
        capture_calls["count"] += 1
        return clients.AdapterResult(False, False, None, "timeout: simulated")

    monkeypatch.setattr(clients, "get_mandate", _get_mandate)
    monkeypatch.setattr(clients, "get_order", _get_order_approved)
    monkeypatch.setattr(clients, "capture_order", _capture_order_timeout)

    first = await client.post(
        f"/orders/{order_id}/capture",
        json={},
        headers={"Idempotency-Key": "capture-2a"},
    )
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "CAPTURE_UNKNOWN"
    assert capture_calls["count"] == 1

    # Reconcile: get_order now reports COMPLETED -- adopt it, never call capture_order again.
    async def _get_order_completed(*a, **k):
        return clients.AdapterResult(
            True,
            True,
            {
                "order_id": paypal_order_id,
                "status": "COMPLETED",
                "custom_id": "22222222-2222-2222-2222-222222222222",
                "invoice_id": order_id,
                "amount_minor": 2000,
                "currency": "USD",
                "capture_ids": ["CAP-reconciled"],
            },
            "ok",
        )

    monkeypatch.setattr(clients, "get_order", _get_order_completed)

    second = await client.post(
        f"/orders/{order_id}/capture",
        json={},
        headers={"Idempotency-Key": "capture-2b"},
    )
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "CAPTURED"
    assert capture_calls["count"] == 1, "capture_order must not be called a second time"


@pytest.mark.asyncio
async def test_capture_revoked_between_approve_and_capture_never_captures(
    client, monkeypatch
) -> None:
    """S2-01: a mandate revoked in the window between PayPal approval and our capture
    call must result in CANCELLED_REVOKED with no capture ever attempted."""
    body, _return_state, _cancel_state = await _create_and_confirm(
        client, monkeypatch, idem="cap-3"
    )
    order_id = body["order_id"]

    async def _get_mandate_revoked(*a, **k):
        m = _active_mandate()
        m["status"] = "revoked"
        return m

    capture_calls = {"count": 0}

    async def _capture_order_should_not_be_called(*a, **k):
        capture_calls["count"] += 1
        raise AssertionError("capture_order must never be called after mandate revoke")

    monkeypatch.setattr(clients, "get_mandate", _get_mandate_revoked)
    monkeypatch.setattr(clients, "capture_order", _capture_order_should_not_be_called)

    resp = await client.post(
        f"/orders/{order_id}/capture", json={}, headers={"Idempotency-Key": "capture-3"}
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"] == "MANDATE_REVOKED"
    assert capture_calls["count"] == 0

    order_resp = await client.get(f"/orders/{order_id}")
    assert order_resp.json()["status"] == "CANCELLED_REVOKED"

    receipt_resp = await client.get(f"/orders/{order_id}/receipt")
    assert receipt_resp.status_code == 409


@pytest.mark.asyncio
async def test_orders_return_capture_flow_and_idempotent_replay(
    client, monkeypatch
) -> None:
    body, return_state, _cancel_state = await _create_and_confirm(
        client, monkeypatch, idem="cap-4"
    )
    order_id = body["order_id"]
    paypal_order_id = "PAY-cap-4"

    async def _get_mandate(*a, **k):
        return _active_mandate()

    async def _get_order(*a, **k):
        return clients.AdapterResult(
            True,
            True,
            {
                "order_id": paypal_order_id,
                "status": "APPROVED",
                "custom_id": "22222222-2222-2222-2222-222222222222",
                "invoice_id": order_id,
                "amount_minor": 2000,
                "currency": "USD",
                "capture_ids": [],
            },
            "ok",
        )

    async def _capture_order(*a, **k):
        return clients.AdapterResult(
            True,
            True,
            {
                "order_id": paypal_order_id,
                "status": "COMPLETED",
                "capture_id": "CAP-4",
                "capture_status": "COMPLETED",
                "custom_id": "22222222-2222-2222-2222-222222222222",
                "invoice_id": order_id,
                "amount_minor": 2000,
                "currency": "USD",
            },
            "captured",
        )

    monkeypatch.setattr(clients, "get_mandate", _get_mandate)
    monkeypatch.setattr(clients, "get_order", _get_order)
    monkeypatch.setattr(clients, "capture_order", _capture_order)

    resp = await client.post(
        "/orders/return",
        json={"state": return_state, "token": paypal_order_id, "payer_id": "PAYER-1"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "CAPTURED"
    assert resp.json()["message_code"] == "CAPTURED"

    # Duplicate return (buyer refreshes the page): idempotent, same result, no error.
    second = await client.post(
        "/orders/return",
        json={"state": return_state, "token": paypal_order_id, "payer_id": "PAYER-1"},
    )
    assert second.status_code == 200
    assert second.json()["order_id"] == resp.json()["order_id"]
    assert second.json()["status"] == "CAPTURED"


@pytest.mark.asyncio
async def test_orders_return_token_mismatch_rejected(client, monkeypatch) -> None:
    body, return_state, _cancel_state = await _create_and_confirm(
        client, monkeypatch, idem="cap-5"
    )
    order_id = body["order_id"]

    resp = await client.post(
        "/orders/return",
        json={"state": return_state, "token": "WRONG-TOKEN", "payer_id": "PAYER-1"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "TOKEN_MISMATCH"

    order_resp = await client.get(f"/orders/{order_id}")
    assert order_resp.json()["status"] == "AWAITING_APPROVAL"


@pytest.mark.asyncio
async def test_orders_return_not_approved_leaves_state_usable_for_retry(
    client, monkeypatch
) -> None:
    body, return_state, _cancel_state = await _create_and_confirm(
        client, monkeypatch, idem="cap-6"
    )
    order_id = body["order_id"]
    paypal_order_id = "PAY-cap-6"

    async def _get_mandate(*a, **k):
        return _active_mandate()

    async def _get_order_not_approved(*a, **k):
        return clients.AdapterResult(
            True,
            True,
            {
                "order_id": paypal_order_id,
                "status": "PAYER_ACTION_REQUIRED",
                "custom_id": "22222222-2222-2222-2222-222222222222",
                "invoice_id": order_id,
                "amount_minor": 2000,
                "currency": "USD",
                "capture_ids": [],
            },
            "ok",
        )

    monkeypatch.setattr(clients, "get_mandate", _get_mandate)
    monkeypatch.setattr(clients, "get_order", _get_order_not_approved)

    first = await client.post(
        "/orders/return",
        json={"state": return_state, "token": paypal_order_id, "payer_id": "PAYER-1"},
    )
    assert first.status_code == 409
    assert first.json()["error"] == "NOT_APPROVED"

    # spec.md section 7 step 6: state must still be usable for a retry.
    async def _get_order_now_approved(*a, **k):
        return clients.AdapterResult(
            True,
            True,
            {
                "order_id": paypal_order_id,
                "status": "APPROVED",
                "custom_id": "22222222-2222-2222-2222-222222222222",
                "invoice_id": order_id,
                "amount_minor": 2000,
                "currency": "USD",
                "capture_ids": [],
            },
            "ok",
        )

    async def _capture_order(*a, **k):
        return clients.AdapterResult(
            True,
            True,
            {
                "order_id": paypal_order_id,
                "status": "COMPLETED",
                "capture_id": "CAP-6",
                "capture_status": "COMPLETED",
                "custom_id": "22222222-2222-2222-2222-222222222222",
                "invoice_id": order_id,
                "amount_minor": 2000,
                "currency": "USD",
            },
            "captured",
        )

    monkeypatch.setattr(clients, "get_order", _get_order_now_approved)
    monkeypatch.setattr(clients, "capture_order", _capture_order)

    second = await client.post(
        "/orders/return",
        json={"state": return_state, "token": paypal_order_id, "payer_id": "PAYER-1"},
    )
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "CAPTURED"


@pytest.mark.asyncio
async def test_orders_cancel_moves_order_to_cancelled_buyer(
    client, monkeypatch
) -> None:
    body, _return_state, cancel_state = await _create_and_confirm(
        client, monkeypatch, idem="cap-7"
    )
    order_id = body["order_id"]

    resp = await client.post("/orders/cancel", json={"state": cancel_state})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "CANCELLED_BUYER"

    order_resp = await client.get(f"/orders/{order_id}")
    assert order_resp.json()["status"] == "CANCELLED_BUYER"


@pytest.mark.asyncio
async def test_receipt_not_ready_before_capture(client, monkeypatch) -> None:
    body, _return_state, _cancel_state = await _create_and_confirm(
        client, monkeypatch, idem="cap-8"
    )
    resp = await client.get(f"/orders/{body['order_id']}/receipt")
    assert resp.status_code == 409
    assert resp.json()["error"] == "RECEIPT_NOT_READY"
