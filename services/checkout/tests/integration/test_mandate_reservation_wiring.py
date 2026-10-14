"""Checkout now calls mandate's real reservation lifecycle (create at confirm,
authorize-capture as the point-of-no-return gate right before the real PayPal
capture call, commit after a successful capture, release/mark-unknown on every
non-capture outcome) -- committed_minor stays as a redundant check, this is the
real cap-enforcement/money-bookkeeping path. See services/checkout/app/clients.py
and app/routers/{carts,orders}.py.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from app import clients


def _extract_state(url: str) -> str:
    return parse_qs(urlparse(url).query)["state"][0]


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


def _active_mandate() -> dict:
    return {
        "status": "active",
        "protection": {
            "kinds_covered": ["LATE", "LOST"],
            "max_refund_minor": 10000,
            "deliver_by_days": 7,
        },
        "remaining_minor": 8000,
    }


async def _create_and_confirm(
    client, monkeypatch, *, idem: str
) -> tuple[dict, str, str]:
    """Returns (confirm_body, return_state, cancel_state)."""

    async def _resolve(*a, **k):
        return _priced_response()

    async def _evaluate(*a, **k):
        return _allow_eval_response()

    captured_urls: dict[str, str] = {}

    async def _create_order(settings, token, *, return_url, cancel_url, **k):
        captured_urls["return_url"] = return_url
        captured_urls["cancel_url"] = cancel_url
        return clients.AdapterResult(
            True,
            True,
            {"order_id": "PAY-" + idem, "approve_url": "https://paypal.test/approve"},
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
    return (
        confirm_resp.json(),
        _extract_state(captured_urls["return_url"]),
        _extract_state(captured_urls["cancel_url"]),
    )


@pytest.mark.asyncio
async def test_authorize_capture_refusal_blocks_the_real_paypal_capture_call(
    client, monkeypatch
) -> None:
    """The point-of-no-return gate: even though get_mandate/get_order both say
    everything is fine, mandate's own authorize-capture refusing must still stop
    the real capture_order call from ever happening."""
    body, _, _ = await _create_and_confirm(client, monkeypatch, idem="resv-gate-1")
    order_id = body["order_id"]

    async def _get_mandate(*a, **k):
        return _active_mandate()

    async def _get_order(*a, **k):
        return clients.AdapterResult(
            True,
            True,
            {
                "order_id": "PAY-resv-gate-1",
                "status": "APPROVED",
                "custom_id": "22222222-2222-2222-2222-222222222222",
                "invoice_id": order_id,
                "amount_minor": 2000,
                "currency": "USD",
                "capture_ids": [],
            },
            "ok",
        )

    async def _authorize_refused(*a, **k):
        return clients.AdapterResult(False, True, {}, "refused", code="MANDATE_REVOKED")

    capture_calls = {"count": 0}

    async def _capture_order_must_not_be_called(*a, **k):
        capture_calls["count"] += 1
        raise AssertionError("capture_order must never be called past a refused gate")

    monkeypatch.setattr(clients, "get_mandate", _get_mandate)
    monkeypatch.setattr(clients, "get_order", _get_order)
    monkeypatch.setattr(clients, "authorize_capture_reservation", _authorize_refused)
    monkeypatch.setattr(clients, "capture_order", _capture_order_must_not_be_called)

    resp = await client.post(
        f"/orders/{order_id}/capture",
        json={},
        headers={"Idempotency-Key": "resv-gate-1-cap"},
    )
    assert resp.status_code == 422, resp.text
    assert capture_calls["count"] == 0

    order_resp = await client.get(f"/orders/{order_id}")
    assert order_resp.json()["status"] == "CANCELLED_REVOKED"
    assert order_resp.json()["failure_code"] == "MANDATE_REVOKED"


@pytest.mark.asyncio
async def test_authorize_capture_unreachable_stays_retryable_not_failed(
    client, monkeypatch
) -> None:
    """mandate being unreachable at this gate must never be treated as a definite
    refusal -- the order stays CAPTURING, safe to retry, never CAPTURE_FAILED."""
    body, _, _ = await _create_and_confirm(client, monkeypatch, idem="resv-gate-2")
    order_id = body["order_id"]

    async def _get_mandate(*a, **k):
        return _active_mandate()

    async def _get_order(*a, **k):
        return clients.AdapterResult(
            True,
            True,
            {
                "order_id": "PAY-resv-gate-2",
                "status": "APPROVED",
                "custom_id": "22222222-2222-2222-2222-222222222222",
                "invoice_id": order_id,
                "amount_minor": 2000,
                "currency": "USD",
                "capture_ids": [],
            },
            "ok",
        )

    async def _authorize_unreachable(*a, **k):
        return clients.AdapterResult(False, False, None, "connection_error")

    capture_calls = {"count": 0}

    async def _capture_order_must_not_be_called(*a, **k):
        capture_calls["count"] += 1
        raise AssertionError(
            "capture_order must never be called past an indefinite gate"
        )

    monkeypatch.setattr(clients, "get_mandate", _get_mandate)
    monkeypatch.setattr(clients, "get_order", _get_order)
    monkeypatch.setattr(
        clients, "authorize_capture_reservation", _authorize_unreachable
    )
    monkeypatch.setattr(clients, "capture_order", _capture_order_must_not_be_called)

    resp = await client.post(
        f"/orders/{order_id}/capture",
        json={},
        headers={"Idempotency-Key": "resv-gate-2-cap"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "CAPTURING"
    assert capture_calls["count"] == 0

    order_resp = await client.get(f"/orders/{order_id}")
    assert order_resp.json()["status"] == "CAPTURING"


@pytest.mark.asyncio
async def test_successful_capture_commits_the_reservation_with_real_amounts(
    client, monkeypatch
) -> None:
    body, _, _ = await _create_and_confirm(client, monkeypatch, idem="resv-commit-1")
    order_id = body["order_id"]

    async def _get_mandate(*a, **k):
        return _active_mandate()

    async def _get_order(*a, **k):
        return clients.AdapterResult(
            True,
            True,
            {
                "order_id": "PAY-resv-commit-1",
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
                "capture_id": "CAP-resv-commit-1",
                "capture_status": "COMPLETED",
                "custom_id": "22222222-2222-2222-2222-222222222222",
                "invoice_id": order_id,
                "amount_minor": 2000,
                "currency": "USD",
            },
            "captured",
        )

    committed: dict = {}

    async def _commit(settings, token, reservation_id, **kwargs):
        committed["reservation_id"] = reservation_id
        committed.update(kwargs)
        return clients.AdapterResult(True, True, {"state": "CAPTURED"}, "ok")

    monkeypatch.setattr(clients, "get_mandate", _get_mandate)
    monkeypatch.setattr(clients, "get_order", _get_order)
    monkeypatch.setattr(clients, "capture_order", _capture_order)
    monkeypatch.setattr(clients, "commit_reservation", _commit)

    resp = await client.post(
        f"/orders/{order_id}/capture",
        json={},
        headers={"Idempotency-Key": "resv-commit-1-cap"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "CAPTURED"

    assert committed["reservation_id"] == "res-test-default"
    assert committed["capture_id"] == "CAP-resv-commit-1"
    assert committed["captured_amount_minor"] == 2000
    assert committed["currency"] == "USD"


@pytest.mark.asyncio
async def test_commit_failure_never_blocks_a_successful_capture(
    client, monkeypatch
) -> None:
    """Money has already moved at PayPal by the time commit is called -- a commit
    failure must never undo or fail the capture response."""
    body, _, _ = await _create_and_confirm(client, monkeypatch, idem="resv-commit-2")
    order_id = body["order_id"]

    async def _get_mandate(*a, **k):
        return _active_mandate()

    async def _get_order(*a, **k):
        return clients.AdapterResult(
            True,
            True,
            {
                "order_id": "PAY-resv-commit-2",
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
                "capture_id": "CAP-resv-commit-2",
                "capture_status": "COMPLETED",
                "custom_id": "22222222-2222-2222-2222-222222222222",
                "invoice_id": order_id,
                "amount_minor": 2000,
                "currency": "USD",
            },
            "captured",
        )

    async def _commit_fails(*a, **k):
        return clients.AdapterResult(False, False, None, "connection_error")

    monkeypatch.setattr(clients, "get_mandate", _get_mandate)
    monkeypatch.setattr(clients, "get_order", _get_order)
    monkeypatch.setattr(clients, "capture_order", _capture_order)
    monkeypatch.setattr(clients, "commit_reservation", _commit_fails)

    resp = await client.post(
        f"/orders/{order_id}/capture",
        json={},
        headers={"Idempotency-Key": "resv-commit-2-cap"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "CAPTURED"


@pytest.mark.asyncio
async def test_cancel_before_capture_releases_the_reservation(
    client, monkeypatch
) -> None:
    body, _return_state, cancel_state = await _create_and_confirm(
        client, monkeypatch, idem="resv-cancel-1"
    )
    order_id = body["order_id"]

    released: dict = {}

    async def _release(settings, token, reservation_id, **kwargs):
        released["reservation_id"] = reservation_id
        released.update(kwargs)
        return clients.AdapterResult(True, True, {"state": "RELEASED"}, "ok")

    monkeypatch.setattr(clients, "release_reservation", _release)

    resp = await client.post("/orders/cancel", json={"state": cancel_state})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "CANCELLED_BUYER"

    order_resp = await client.get(f"/orders/{order_id}")
    assert order_resp.json()["status"] == "CANCELLED_BUYER"
    assert released["reservation_id"] == "res-test-default"
    assert released["reason_code"] == "CANCELLED_BUYER"
