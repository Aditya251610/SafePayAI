"""Integration tests against a real Postgres (see conftest.py). catalog/mandate/adapter
calls are monkeypatched at the app.clients function level - no real network - so these
tests exercise checkout's own DB/transaction logic (R4 ordering, idempotency, CAS) for
real, which is the part unit tests can't cover.
"""

from __future__ import annotations

import pytest

from app import clients


def _priced_response(total_minor: int = 500) -> dict:
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


def _allow_eval_response() -> dict:
    return {
        "decision": "ALLOW",
        "hard_blocks": [],
        "advisory_flags": [],
        "mandate": {
            "mandate_id": "22222222-2222-2222-2222-222222222222",
            "mandate_hash": "hash-1",
            "status": "active",
            "remaining_minor": 10000,
            "policy_version": "v1",
        },
        "evaluated_at": "2026-01-01T00:00:00Z",
    }


def _block_eval_response() -> dict:
    return {
        "decision": "BLOCK",
        # Real mandate shape (mandate_logic.EvaluateResult.hard_blocks): list of
        # {"code": str, "details": dict}, never bare strings -- this fixture previously
        # mocked the wrong shape, which is exactly why create_cart's old bare-string
        # handling of hard_blocks was never caught as broken.
        "hard_blocks": [{"code": "OVER_CAP", "details": {"remaining_minor": 0}}],
        "advisory_flags": [],
        "mandate": {
            "mandate_id": "22222222-2222-2222-2222-222222222222",
            "mandate_hash": "hash-1",
            "status": "active",
            "remaining_minor": 0,
            "policy_version": "v1",
        },
        "evaluated_at": "2026-01-01T00:00:00Z",
    }


@pytest.mark.asyncio
async def test_create_cart_checked_on_allow(client, monkeypatch) -> None:
    monkeypatch.setattr(clients, "resolve_prices", lambda *a, **k: _priced_response())
    monkeypatch.setattr(
        clients, "evaluate_mandate", lambda *a, **k: _allow_eval_response()
    )

    async def _resolve(*a, **k):
        return _priced_response()

    async def _evaluate(*a, **k):
        return _allow_eval_response()

    monkeypatch.setattr(clients, "resolve_prices", _resolve)
    monkeypatch.setattr(clients, "evaluate_mandate", _evaluate)

    resp = await client.post(
        "/carts",
        json={
            "mandate_id": "22222222-2222-2222-2222-222222222222",
            "lines": [{"sku": "sku-1", "qty": 1}],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "CHECKED"
    assert body["total_minor"] == 500


@pytest.mark.asyncio
async def test_create_cart_blocked_on_mandate_block(client, monkeypatch) -> None:
    async def _resolve(*a, **k):
        return _priced_response()

    async def _evaluate(*a, **k):
        return _block_eval_response()

    monkeypatch.setattr(clients, "resolve_prices", _resolve)
    monkeypatch.setattr(clients, "evaluate_mandate", _evaluate)

    resp = await client.post(
        "/carts",
        json={
            "mandate_id": "22222222-2222-2222-2222-222222222222",
            "lines": [{"sku": "sku-1", "qty": 1}],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "BLOCKED"
    assert "OVER_CAP" in [c["reason_code"] for c in body["checks"]]


@pytest.mark.asyncio
async def test_create_cart_blocked_fail_closed_when_mandate_down(
    client, monkeypatch
) -> None:
    """Golden rule: mandate unreachable must BLOCK, never fail open."""

    async def _resolve(*a, **k):
        return _priced_response()

    async def _evaluate(*a, **k):
        raise clients.UpstreamError("mandate", "connection refused")

    monkeypatch.setattr(clients, "resolve_prices", _resolve)
    monkeypatch.setattr(clients, "evaluate_mandate", _evaluate)

    resp = await client.post(
        "/carts",
        json={
            "mandate_id": "22222222-2222-2222-2222-222222222222",
            "lines": [{"sku": "sku-1", "qty": 1}],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "BLOCKED"
    assert "MANDATE_UNAVAILABLE" in [c["reason_code"] for c in body["checks"]]


@pytest.mark.asyncio
async def test_create_cart_blocked_fail_closed_when_catalog_down(
    client, monkeypatch
) -> None:
    async def _resolve(*a, **k):
        raise clients.UpstreamError("catalog", "connection refused")

    monkeypatch.setattr(clients, "resolve_prices", _resolve)

    resp = await client.post(
        "/carts",
        json={
            "mandate_id": "22222222-2222-2222-2222-222222222222",
            "lines": [{"sku": "sku-1", "qty": 1}],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "BLOCKED"
    assert "CATALOG_UNAVAILABLE" in [c["reason_code"] for c in body["checks"]]


@pytest.mark.asyncio
async def test_confirm_writes_order_before_adapter_call_then_awaiting_approval(
    client, monkeypatch
) -> None:
    """R4: order row exists (CREATING) before the adapter call; this test observes the
    end-to-end result (AWAITING_APPROVAL) and that create_order was actually invoked
    after cart creation completed."""

    async def _resolve(*a, **k):
        return _priced_response()

    async def _evaluate(*a, **k):
        return _allow_eval_response()

    call_order: list[str] = []

    async def _create_order(*a, **k):
        call_order.append("adapter_create_order")
        return clients.AdapterResult(
            True,
            True,
            {"order_id": "PAY-1", "approve_url": "https://paypal.test/approve"},
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
        headers={"Idempotency-Key": "idem-1"},
    )
    assert confirm_resp.status_code == 201, confirm_resp.text
    body = confirm_resp.json()
    assert body["status"] == "AWAITING_APPROVAL"
    assert body["approve_url"] == "https://paypal.test/approve"
    assert call_order == ["adapter_create_order"]

    order_resp = await client.get(f"/orders/{body['order_id']}")
    assert order_resp.status_code == 200
    assert order_resp.json()["status"] == "AWAITING_APPROVAL"


@pytest.mark.asyncio
async def test_confirm_adapter_down_yields_create_unknown_not_lost(
    client, monkeypatch
) -> None:
    """R4 in the failure case: if the adapter call fails, the order row must already
    exist (we can observe it via GET) and move to CREATE_UNKNOWN - never silently lost."""

    async def _resolve(*a, **k):
        return _priced_response()

    async def _evaluate(*a, **k):
        return _allow_eval_response()

    async def _create_order(*a, **k):
        return clients.AdapterResult(False, False, None, "connection_error: refused")

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
        headers={"Idempotency-Key": "idem-2"},
    )
    assert confirm_resp.status_code == 502
    order_id = confirm_resp.json()["details"]["order_id"]

    order_resp = await client.get(f"/orders/{order_id}")
    assert order_resp.status_code == 200
    assert order_resp.json()["status"] == "CREATE_UNKNOWN"


@pytest.mark.asyncio
async def test_confirm_idempotent_replay_same_key(client, monkeypatch) -> None:
    async def _resolve(*a, **k):
        return _priced_response()

    async def _evaluate(*a, **k):
        return _allow_eval_response()

    async def _create_order(*a, **k):
        return clients.AdapterResult(
            True,
            True,
            {"order_id": "PAY-2", "approve_url": "https://paypal.test/approve2"},
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

    first = await client.post(
        f"/carts/{cart_body['cart_id']}/confirm",
        json={"proposal_hash": cart_body["proposal_hash"]},
        headers={"Idempotency-Key": "idem-3"},
    )
    second = await client.post(
        f"/carts/{cart_body['cart_id']}/confirm",
        json={"proposal_hash": cart_body["proposal_hash"]},
        headers={"Idempotency-Key": "idem-3"},
    )
    assert first.json()["order_id"] == second.json()["order_id"]


async def _create_confirmed_order(client, monkeypatch, *, idem_key: str) -> str:
    async def _resolve(*a, **k):
        return _priced_response()

    async def _evaluate(*a, **k):
        return _allow_eval_response()

    async def _create_order(*a, **k):
        return clients.AdapterResult(
            True,
            True,
            {"order_id": f"PAY-{idem_key}", "approve_url": "https://x"},
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
        headers={"Idempotency-Key": idem_key},
    )
    return confirm_resp.json()["order_id"]


def _override_principal(role: str, merchant_id: str | None = None) -> None:
    from app.deps import Principal, require_service_jwt
    from app.main import app

    app.dependency_overrides[require_service_jwt] = lambda: Principal(
        sub="test-" + role,
        role=role,
        buyer_id="11111111-1111-1111-1111-111111111111",
        merchant_id=merchant_id,
    )


@pytest.mark.asyncio
async def test_list_orders_buyer_scoped_to_own_orders(client, monkeypatch) -> None:
    order_id = await _create_confirmed_order(
        client, monkeypatch, idem_key="idem-list-1"
    )

    resp = await client.get(
        "/orders", params={"mandate_id": "22222222-2222-2222-2222-222222222222"}
    )
    assert resp.status_code == 200
    order_ids = {item["order_id"] for item in resp.json()["items"]}
    assert order_id in order_ids


@pytest.mark.asyncio
async def test_list_orders_merchant_scoped_to_own_merchant_id(
    client, monkeypatch
) -> None:
    order_id = await _create_confirmed_order(
        client, monkeypatch, idem_key="idem-list-2"
    )

    _override_principal("merchant", merchant_id="merchant-1")
    resp = await client.get(
        "/orders", params={"mandate_id": "22222222-2222-2222-2222-222222222222"}
    )
    assert resp.status_code == 200
    order_ids = {item["order_id"] for item in resp.json()["items"]}
    assert order_id in order_ids

    _override_principal("merchant", merchant_id="some-other-merchant")
    resp = await client.get(
        "/orders", params={"mandate_id": "22222222-2222-2222-2222-222222222222"}
    )
    assert resp.status_code == 200
    assert order_id not in {item["order_id"] for item in resp.json()["items"]}


@pytest.mark.asyncio
async def test_list_orders_merchant_without_merchant_id_fails_closed(
    client, monkeypatch
) -> None:
    await _create_confirmed_order(client, monkeypatch, idem_key="idem-list-3")

    _override_principal("merchant", merchant_id=None)
    resp = await client.get(
        "/orders", params={"mandate_id": "22222222-2222-2222-2222-222222222222"}
    )
    assert resp.status_code == 200
    assert resp.json()["items"] == []


@pytest.mark.asyncio
async def test_confirm_blocked_when_mandate_refuses_reservation(
    client, monkeypatch
) -> None:
    async def _resolve(*a, **k):
        return _priced_response()

    async def _evaluate(*a, **k):
        return _allow_eval_response()

    async def _refused(*a, **k):
        return clients.AdapterResult(False, True, {}, "refused", code="OVER_CAP")

    monkeypatch.setattr(clients, "resolve_prices", _resolve)
    monkeypatch.setattr(clients, "evaluate_mandate", _evaluate)
    monkeypatch.setattr(clients, "create_reservation", _refused)

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
        headers={"Idempotency-Key": "idem-reservation-refused"},
    )
    assert confirm_resp.status_code == 409
    assert confirm_resp.json()["error"] == "OVER_CAP"
    # No order was ever created for THIS cart -- a refused reservation must not
    # leave a row behind (other tests in this session create their own orders
    # under the same shared mandate_id, so check by cart_id, not list emptiness).
    order_resp = await client.get(
        "/orders", params={"mandate_id": "22222222-2222-2222-2222-222222222222"}
    )
    cart_ids = {item["cart_id"] for item in order_resp.json()["items"]}
    assert cart_body["cart_id"] not in cart_ids


@pytest.mark.asyncio
async def test_confirm_blocked_when_mandate_unreachable_for_reservation(
    client, monkeypatch
) -> None:
    async def _resolve(*a, **k):
        return _priced_response()

    async def _evaluate(*a, **k):
        return _allow_eval_response()

    async def _unreachable(*a, **k):
        return clients.AdapterResult(False, False, None, "connection_error")

    monkeypatch.setattr(clients, "resolve_prices", _resolve)
    monkeypatch.setattr(clients, "evaluate_mandate", _evaluate)
    monkeypatch.setattr(clients, "create_reservation", _unreachable)

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
        headers={"Idempotency-Key": "idem-reservation-unreachable"},
    )
    assert confirm_resp.status_code == 503
    assert confirm_resp.json()["error"] == "MANDATE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_confirm_stores_mandate_reservation_id_on_the_order(
    client, monkeypatch
) -> None:
    async def _resolve(*a, **k):
        return _priced_response()

    async def _evaluate(*a, **k):
        return _allow_eval_response()

    async def _create_order(*a, **k):
        return clients.AdapterResult(
            True, True, {"order_id": "PAY-resv", "approve_url": "https://x"}, "created"
        )

    async def _reserved(*a, **k):
        return clients.AdapterResult(
            True, True, {"reservation_id": "res-abc-123", "state": "RESERVED"}, "ok"
        )

    monkeypatch.setattr(clients, "resolve_prices", _resolve)
    monkeypatch.setattr(clients, "evaluate_mandate", _evaluate)
    monkeypatch.setattr(clients, "create_order", _create_order)
    monkeypatch.setattr(clients, "create_reservation", _reserved)

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
        headers={"Idempotency-Key": "idem-reservation-stored"},
    )
    assert confirm_resp.status_code == 201
    order_id = confirm_resp.json()["order_id"]

    order_resp = await client.get(f"/orders/{order_id}")
    assert order_resp.json()["mandate_reservation_id"] == "res-abc-123"
