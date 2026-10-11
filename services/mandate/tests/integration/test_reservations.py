"""Reservation ledger (spec.md section 7): reserve/authorize/commit/release,
natural-key idempotency, OVER_CAP refusal under the row lock."""

from __future__ import annotations

import uuid

from tests.integration.helpers import preview_and_sign, sample_cart


async def _sign(client, buyer_token, **overrides):
    return await preview_and_sign(client, buyer_token, str(uuid.uuid4()), **overrides)


async def test_reserve_authorize_commit_happy_path(client, buyer_token, service_token):
    svc = service_token()
    mandate = await _sign(client, buyer_token())
    mandate_id = mandate["mandate_id"]
    order_id = str(uuid.uuid4())

    reserve = await client.post(
        f"/mandates/{mandate_id}/reservations",
        json={
            "order_id": order_id,
            "amount_minor": 2500,
            "currency": "USD",
            "proposal_hash": "h" * 10,
            "cart": sample_cart(),
        },
        headers={"Authorization": f"Bearer {svc}"},
    )
    assert reserve.status_code == 201
    assert reserve.json()["mandate"]["reserved_minor"] == 2500
    reservation_id = reserve.json()["reservation_id"]

    authorize = await client.post(
        f"/reservations/{reservation_id}/authorize-capture",
        json={"order_id": order_id, "amount_minor": 2500},
        headers={"Authorization": f"Bearer {svc}"},
    )
    assert authorize.status_code == 200, authorize.text
    assert authorize.json()["state"] == "CAPTURING"

    commit = await client.post(
        f"/reservations/{reservation_id}/commit",
        json={
            "capture_id": "CAP-1",
            "captured_amount_minor": 2500,
            "currency": "USD",
            "captured_at": "2026-10-20T10:07:00Z",
        },
        headers={"Authorization": f"Bearer {svc}"},
    )
    assert commit.status_code == 200
    body = commit.json()
    assert body["state"] == "CAPTURED"
    assert body["mandate"]["spent_minor"] == 2500
    assert body["mandate"]["reserved_minor"] == 0
    assert body["protection"]["terms_hash"]


async def test_reserve_same_order_id_is_idempotent(client, buyer_token, service_token):
    svc = service_token()
    mandate = await _sign(client, buyer_token())
    mandate_id = mandate["mandate_id"]
    order_id = str(uuid.uuid4())
    payload = {
        "order_id": order_id,
        "amount_minor": 2500,
        "currency": "USD",
        "proposal_hash": "h" * 10,
        "cart": sample_cart(),
    }

    first = await client.post(
        f"/mandates/{mandate_id}/reservations",
        json=payload,
        headers={"Authorization": f"Bearer {svc}"},
    )
    assert first.status_code == 201
    second = await client.post(
        f"/mandates/{mandate_id}/reservations",
        json=payload,
        headers={"Authorization": f"Bearer {svc}"},
    )
    assert second.status_code == 200
    assert second.json()["reservation_id"] == first.json()["reservation_id"]


async def test_reserve_same_order_id_different_amount_is_conflict(
    client, buyer_token, service_token
):
    svc = service_token()
    mandate = await _sign(client, buyer_token())
    mandate_id = mandate["mandate_id"]
    order_id = str(uuid.uuid4())
    base = {
        "order_id": order_id,
        "currency": "USD",
        "proposal_hash": "h" * 10,
        "cart": sample_cart(),
    }

    first = await client.post(
        f"/mandates/{mandate_id}/reservations",
        json={**base, "amount_minor": 2500},
        headers={"Authorization": f"Bearer {svc}"},
    )
    assert first.status_code == 201
    second = await client.post(
        f"/mandates/{mandate_id}/reservations",
        json={**base, "amount_minor": 3000},
        headers={"Authorization": f"Bearer {svc}"},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "RESERVATION_CONFLICT"


async def test_reserve_over_cap_is_refused(client, buyer_token, service_token):
    svc = service_token()
    mandate = await _sign(client, buyer_token())
    mandate_id = mandate["mandate_id"]
    cart = sample_cart(
        total_minor=7000,
        lines=[
            {
                "sku": "sku-1",
                "qty": 1,
                "unit_minor": 7000,
                "line_minor": 7000,
                "merchant_id": "shop-a",
                "sku_known": True,
                "stated_unit_minor": 7000,
            }
        ],
    )
    resp = await client.post(
        f"/mandates/{mandate_id}/reservations",
        json={
            "order_id": str(uuid.uuid4()),
            "amount_minor": 7000,
            "currency": "USD",
            "proposal_hash": "h" * 10,
            "cart": cart,
        },
        headers={"Authorization": f"Bearer {svc}"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "RESERVATION_REFUSED"
    codes = [b["code"] for b in resp.json()["error"]["details"]["hard_blocks"]]
    assert "OVER_CAP" in codes


async def test_release_gives_cap_back(client, buyer_token, service_token):
    svc = service_token()
    mandate = await _sign(client, buyer_token())
    mandate_id = mandate["mandate_id"]
    order_id = str(uuid.uuid4())
    reserve = (
        await client.post(
            f"/mandates/{mandate_id}/reservations",
            json={
                "order_id": order_id,
                "amount_minor": 2500,
                "currency": "USD",
                "proposal_hash": "h" * 10,
                "cart": sample_cart(),
            },
            headers={"Authorization": f"Bearer {svc}"},
        )
    ).json()

    release = await client.post(
        f"/reservations/{reserve['reservation_id']}/release",
        json={"reason_code": "BUYER_CANCELLED"},
        headers={"Authorization": f"Bearer {svc}"},
    )
    assert release.status_code == 200
    assert release.json()["state"] == "RELEASED"

    summary = await client.get(
        f"/mandates/{mandate_id}/summary", headers={"Authorization": f"Bearer {svc}"}
    )
    assert summary.json()["reserved_minor"] == 0
    assert summary.json()["remaining_minor"] == 6000


async def test_commit_amount_mismatch_is_409(client, buyer_token, service_token):
    svc = service_token()
    mandate = await _sign(client, buyer_token())
    mandate_id = mandate["mandate_id"]
    order_id = str(uuid.uuid4())
    reserve = (
        await client.post(
            f"/mandates/{mandate_id}/reservations",
            json={
                "order_id": order_id,
                "amount_minor": 2500,
                "currency": "USD",
                "proposal_hash": "h" * 10,
                "cart": sample_cart(),
            },
            headers={"Authorization": f"Bearer {svc}"},
        )
    ).json()
    await client.post(
        f"/reservations/{reserve['reservation_id']}/authorize-capture",
        json={"order_id": order_id, "amount_minor": 2500},
        headers={"Authorization": f"Bearer {svc}"},
    )
    commit = await client.post(
        f"/reservations/{reserve['reservation_id']}/commit",
        json={
            "capture_id": "CAP-X",
            "captured_amount_minor": 1,
            "currency": "USD",
            "captured_at": "2026-10-20T10:07:00Z",
        },
        headers={"Authorization": f"Bearer {svc}"},
    )
    assert commit.status_code == 409
    assert commit.json()["error"]["code"] == "AMOUNT_MISMATCH"
