"""Integration tests for POST /internal/events, GET /internal/outbox, and
POST /internal/reconcile (api.md section 10) -- previously 501 stubs. mandate/paypal-adapter
calls are monkeypatched at the app_checkout.clients function level, same pattern as
test_capture_return_cancel.py; these exercise checkout's own DB/transaction logic for real.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app_checkout import clients


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


def _allow_eval_response(mandate_id: str) -> dict:
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


def _mandate_event(event_id: str, mandate_id: str) -> dict:
    return {
        "event_id": event_id,
        "type": "mandate.revoked",
        "version": 1,
        "occurred_at": "2026-01-01T00:00:00Z",
        "producer": "mandate",
        "aggregate_id": mandate_id,
        "trace_id": str(uuid.uuid4()),
        "payload": {"mandate_id": mandate_id},
    }


@pytest.mark.asyncio
async def test_internal_events_mandate_revoked_blocks_matching_carts(
    client, monkeypatch
) -> None:
    mandate_id = "33333333-3333-3333-3333-333333333333"

    async def _resolve(*a, **k):
        return _priced_response()

    async def _evaluate(*a, **k):
        return _allow_eval_response(mandate_id)

    monkeypatch.setattr(clients, "resolve_prices", _resolve)
    monkeypatch.setattr(clients, "evaluate_mandate", _evaluate)

    cart_resp = await client.post(
        "/carts", json={"mandate_id": mandate_id, "lines": [{"sku": "sku-1", "qty": 1}]}
    )
    assert cart_resp.status_code == 201, cart_resp.text
    assert cart_resp.json()["status"] == "CHECKED"

    resp = await client.post(
        "/internal/events", json=_mandate_event(str(uuid.uuid4()), mandate_id)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["handled"] is True
    assert body["carts_blocked"] == 1
    # Note: this only proves the EXISTING cart got blocked, not that a NEW cart under the
    # same revoked mandate would be rejected at creation -- that's mandate's own /evaluate
    # call's job (mocked above to always ALLOW in this test), not this endpoint's.


@pytest.mark.asyncio
async def test_internal_events_duplicate_event_id_is_noop(client, monkeypatch) -> None:
    mandate_id = "44444444-4444-4444-4444-444444444444"

    async def _resolve(*a, **k):
        return _priced_response()

    async def _evaluate(*a, **k):
        return _allow_eval_response(mandate_id)

    monkeypatch.setattr(clients, "resolve_prices", _resolve)
    monkeypatch.setattr(clients, "evaluate_mandate", _evaluate)

    await client.post(
        "/carts", json={"mandate_id": mandate_id, "lines": [{"sku": "sku-1", "qty": 1}]}
    )

    event_id = str(uuid.uuid4())
    event = _mandate_event(event_id, mandate_id)

    resp1 = await client.post("/internal/events", json=event)
    assert resp1.status_code == 200
    assert resp1.json()["carts_blocked"] == 1

    resp2 = await client.post("/internal/events", json=event)
    assert resp2.status_code == 200
    assert resp2.json()["duplicate"] is True
    assert "carts_blocked" not in resp2.json()


@pytest.mark.asyncio
async def test_internal_events_unknown_type_is_noop(client) -> None:
    event = {
        "event_id": str(uuid.uuid4()),
        "type": "some.unknown.event",
        "version": 1,
        "occurred_at": "2026-01-01T00:00:00Z",
        "producer": "mandate",
        "aggregate_id": str(uuid.uuid4()),
        "trace_id": None,
        "payload": {},
    }
    resp = await client.post("/internal/events", json=event)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["handled"] is False


@pytest.mark.asyncio
async def test_internal_outbox_returns_events_after_seq(client, db_engine) -> None:
    # No cross-test DB cleanup in this suite (matches the rest of checkout's integration
    # tests -- unique ids per test, not a clean slate), so this test anchors on the max
    # seq already present rather than assuming it starts at 0.
    async with db_engine.connect() as conn:
        baseline = (
            await conn.execute(
                text("SELECT COALESCE(MAX(seq), 0) FROM checkout.outbox")
            )
        ).scalar_one()
        for _ in range(3):
            await conn.execute(
                text(
                    "INSERT INTO checkout.outbox (event_id, type, version, aggregate_id, "
                    "payload, trace_id) VALUES (:event_id, 'cart.created', 1, :aggregate_id, "
                    "CAST(:payload AS jsonb), :trace_id)"
                ),
                {
                    "event_id": str(uuid.uuid4()),
                    "aggregate_id": str(uuid.uuid4()),
                    "payload": "{}",
                    "trace_id": str(uuid.uuid4()),
                },
            )
        await conn.commit()

    resp = await client.get(f"/internal/outbox?after={baseline}")
    assert resp.status_code == 200, resp.text
    events = resp.json()["events"]
    assert len(events) == 3

    resp2 = await client.get(f"/internal/outbox?after={events[0]['seq']}")
    assert resp2.status_code == 200
    assert len(resp2.json()["events"]) == 2


@pytest.mark.asyncio
async def test_internal_reconcile_advances_a_stuck_order(client, monkeypatch) -> None:
    mandate_id = "55555555-5555-5555-5555-555555555555"

    async def _resolve(*a, **k):
        return _priced_response()

    async def _evaluate(*a, **k):
        return _allow_eval_response(mandate_id)

    captured_urls: dict[str, str] = {}

    async def _create_order(settings, token, *, return_url, cancel_url, **k):
        captured_urls["return_url"] = return_url
        return clients.AdapterResult(
            True,
            True,
            {
                "order_id": "PAY-RECONCILE-1",
                "approve_url": "https://paypal.test/approve",
            },
            "created",
        )

    monkeypatch.setattr(clients, "resolve_prices", _resolve)
    monkeypatch.setattr(clients, "evaluate_mandate", _evaluate)
    monkeypatch.setattr(clients, "create_order", _create_order)

    cart_resp = await client.post(
        "/carts", json={"mandate_id": mandate_id, "lines": [{"sku": "sku-1", "qty": 1}]}
    )
    cart_body = cart_resp.json()
    confirm_resp = await client.post(
        f"/carts/{cart_body['cart_id']}/confirm",
        json={"proposal_hash": cart_body["proposal_hash"]},
        headers={"Idempotency-Key": "reconcile-confirm-1"},
    )
    assert confirm_resp.status_code == 201, confirm_resp.text
    order_id = confirm_resp.json()["order_id"]
    # Order is now AWAITING_APPROVAL -- simulating a buyer who approved on PayPal but
    # never completed the return redirect (closed the tab).

    async def _get_mandate(*a, **k):
        return {
            "mandate_id": mandate_id,
            "status": "active",
            "remaining_minor": 8000,
            "protection": {
                "kinds_covered": ["late"],
                "max_refund_minor": 5000,
                "deliver_by_days": 14,
            },
        }

    async def _get_order(*a, **k):
        return clients.AdapterResult(
            True,
            True,
            {
                "order_id": "PAY-RECONCILE-1",
                "status": "APPROVED",
                "custom_id": mandate_id,
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
                "order_id": "PAY-RECONCILE-1",
                "status": "COMPLETED",
                "capture_id": "CAP-RECONCILE-1",
                "capture_status": "COMPLETED",
                "custom_id": mandate_id,
                "invoice_id": order_id,
                "amount_minor": 2000,
                "currency": "USD",
            },
            "captured",
        )

    monkeypatch.setattr(clients, "get_mandate", _get_mandate)
    monkeypatch.setattr(clients, "get_order", _get_order)
    monkeypatch.setattr(clients, "capture_order", _capture_order)

    resp = await client.post("/internal/reconcile")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Other integration test files in the same run may leave their own stuck orders
    # behind (no cross-test DB cleanup in this suite, matching the rest of checkout's
    # tests), so this only asserts that at least this test's own order was examined and
    # reached a terminal state -- not an exact global count.
    assert body["examined"] >= 1

    order_resp = await client.get(f"/orders/{order_id}")
    assert order_resp.status_code == 200
    assert order_resp.json()["status"] == "CAPTURED"
