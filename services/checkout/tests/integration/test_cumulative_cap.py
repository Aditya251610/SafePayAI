"""Cumulative mandate-cap enforcement (spec.md sec 4 step 6) -- previously
`carts.py` hardcoded `committed_minor=0` on every call to mandate's /evaluate, and
`repo.sum_committed_minor` (which sums total_minor across this mandate's in-flight/
completed orders) was defined but never called. A mandate's cap was therefore only ever
checked against a single cart in isolation: any number of individually-under-cap carts
could be confirmed into orders without limit.

This test proves the real wiring: confirm one cart into an order (AWAITING_APPROVAL,
counted by sum_committed_minor), then create a second cart under the same mandate and
assert /carts passes the first order's real total as `committed_minor` -- not 0 -- to
mandate's /evaluate. The mock below enforces the same cap math mandate's own /evaluate
handler now does (see services/mandate/app/routers/mandates.py), so this also proves the
end-to-end behavior: a second cart that was fine in isolation is correctly BLOCKED once
prior committed spend is accounted for.
"""

from __future__ import annotations

import uuid

import pytest

from app import clients

CAP_MINOR = 3000


def _priced_response(total_minor: int) -> dict:
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


def _eval_response_enforcing_cap(
    cart: dict, committed_minor: int, mandate_id: str
) -> dict:
    """Mirrors mandate's own real cap math (remaining = cap - committed_minor)."""
    remaining = max(0, CAP_MINOR - committed_minor)
    over_cap = cart["total_minor"] > remaining
    return {
        "decision": "BLOCK" if over_cap else "ALLOW",
        "hard_blocks": (
            [{"code": "OVER_CAP", "details": {"remaining_minor": remaining}}]
            if over_cap
            else []
        ),
        "advisory_flags": [],
        "mandate": {
            "mandate_id": mandate_id,
            "mandate_hash": "hash-1",
            "status": "active",
            "remaining_minor": remaining,
            "policy_version": "v1",
        },
        "evaluated_at": "2026-01-01T00:00:00Z",
    }


@pytest.mark.asyncio
async def test_second_cart_blocked_once_prior_order_consumes_cap(
    client, monkeypatch
) -> None:
    # Unique per test run -- sum_committed_minor sums real checkout.orders rows scoped
    # to this exact mandate_id, so a shared/hardcoded id would pick up other tests'
    # orders too (no cross-test DB cleanup in this suite, see other test files' notes).
    mandate_id = str(uuid.uuid4())
    seen_committed_minor: list[int] = []

    async def _resolve(*a, **k):
        return _priced_response(2000)

    async def _evaluate(settings, token, mandate_id_arg, cart, committed_minor=None):
        seen_committed_minor.append(committed_minor or 0)
        return _eval_response_enforcing_cap(cart, committed_minor or 0, mandate_id_arg)

    async def _create_order(settings, token, *, return_url, cancel_url, **k):
        return clients.AdapterResult(
            True,
            True,
            {"order_id": "PAY-CAP-1", "approve_url": "https://paypal.test/approve"},
            "created",
        )

    monkeypatch.setattr(clients, "resolve_prices", _resolve)
    monkeypatch.setattr(clients, "evaluate_mandate", _evaluate)
    monkeypatch.setattr(clients, "create_order", _create_order)

    # First cart: 2000 against a 3000 cap, no prior committed spend -- allowed.
    cart_resp = await client.post(
        "/carts", json={"mandate_id": mandate_id, "lines": [{"sku": "sku-1", "qty": 1}]}
    )
    assert cart_resp.status_code == 201, cart_resp.text
    cart_body = cart_resp.json()
    assert cart_body["status"] == "CHECKED"
    assert seen_committed_minor[-1] == 0

    confirm_resp = await client.post(
        f"/carts/{cart_body['cart_id']}/confirm",
        json={"proposal_hash": cart_body["proposal_hash"]},
        headers={"Idempotency-Key": "cap-confirm-1"},
    )
    assert confirm_resp.status_code == 201, confirm_resp.text
    # Order is now AWAITING_APPROVAL -- counted by sum_committed_minor.

    # Second cart: another 2000 against the same 3000 cap. In isolation this would be
    # ALLOWed (2000 <= 3000); with the first order's 2000 correctly reported as
    # committed_minor, cumulative spend would be 4000 > 3000 -- BLOCKED.
    cart_resp_2 = await client.post(
        "/carts", json={"mandate_id": mandate_id, "lines": [{"sku": "sku-1", "qty": 1}]}
    )
    assert cart_resp_2.status_code == 201, cart_resp_2.text
    assert seen_committed_minor[-1] == 2000
    body_2 = cart_resp_2.json()
    assert body_2["status"] == "BLOCKED"
    assert any(
        c["name"] == "mandate_evaluate" and c["result"] == "BLOCK"
        for c in body_2["checks"]
    )
