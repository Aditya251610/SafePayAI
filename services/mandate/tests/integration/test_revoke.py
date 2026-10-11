"""D1 (platform PRD sec 12): revoke stops future spend only; protection already
earned on captured orders stands. Behavior table in spec.md section 8."""

from __future__ import annotations

import uuid

from tests.integration.helpers import preview_and_sign, sample_cart


async def test_revoke_releases_reserved_and_blocks_later_authorize(
    client, buyer_token, service_token
):
    buyer = buyer_token()
    svc = service_token()
    mandate = await preview_and_sign(client, buyer, str(uuid.uuid4()))
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
    assert reserve.status_code == 201, reserve.text
    reservation_id = reserve.json()["reservation_id"]

    revoke = await client.post(
        f"/mandates/{mandate_id}/revoke",
        json={"reason_code": "BUYER_REQUEST"},
        headers={"Authorization": f"Bearer {buyer}"},
    )
    assert revoke.status_code == 200
    assert revoke.json()["status"] == "revoked"
    assert revoke.json()["released_reservations"] == 1

    authorize = await client.post(
        f"/reservations/{reservation_id}/authorize-capture",
        json={"order_id": order_id, "amount_minor": 2500},
        headers={"Authorization": f"Bearer {svc}"},
    )
    assert authorize.status_code == 409
    assert authorize.json()["error"]["code"] in (
        "MANDATE_REVOKED",
        "INVALID_RESERVATION_STATE",
    )


async def test_revoke_is_idempotent_no_second_event(client, buyer_token):
    buyer = buyer_token()
    mandate = await preview_and_sign(client, buyer, str(uuid.uuid4()))
    mandate_id = mandate["mandate_id"]

    first = await client.post(
        f"/mandates/{mandate_id}/revoke",
        json={"reason_code": "BUYER_REQUEST"},
        headers={"Authorization": f"Bearer {buyer}"},
    )
    second = await client.post(
        f"/mandates/{mandate_id}/revoke",
        json={"reason_code": "BUYER_REQUEST"},
        headers={"Authorization": f"Bearer {buyer}"},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["revoked_at"] == second.json()["revoked_at"]


async def test_revoke_after_capture_does_not_block_commit_and_grant_stands(
    client, buyer_token, service_token
):
    buyer = buyer_token()
    svc = service_token()
    mandate = await preview_and_sign(client, buyer, str(uuid.uuid4()))
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
    reservation_id = reserve["reservation_id"]

    authorize = await client.post(
        f"/reservations/{reservation_id}/authorize-capture",
        json={"order_id": order_id, "amount_minor": 2500},
        headers={"Authorization": f"Bearer {svc}"},
    )
    assert authorize.status_code == 200

    # Revoke races in after authorize already won the lock (spec.md section 8 table row 3).
    revoke = await client.post(
        f"/mandates/{mandate_id}/revoke",
        json={"reason_code": "BUYER_REQUEST"},
        headers={"Authorization": f"Bearer {buyer}"},
    )
    assert revoke.status_code == 200

    commit = await client.post(
        f"/reservations/{reservation_id}/commit",
        json={
            "capture_id": "CAPTURE-1",
            "captured_amount_minor": 2500,
            "currency": "USD",
            "captured_at": "2026-10-20T10:07:00Z",
        },
        headers={"Authorization": f"Bearer {svc}"},
    )
    assert commit.status_code == 200, commit.text
    grant_id = commit.json()["grant_id"]
    assert grant_id

    grant = await client.get(
        f"/grants?order_id={order_id}", headers={"Authorization": f"Bearer {svc}"}
    )
    assert grant.status_code == 200
    assert grant.json()["protection_in_force"] is True
    assert grant.json()["mandate_status"] == "revoked"


async def test_revoke_on_already_expired_mandate_is_noop(client, buyer_token, db_conn):
    buyer = buyer_token()
    mandate = await preview_and_sign(client, buyer, str(uuid.uuid4()))
    mandate_id = mandate["mandate_id"]

    # Status is derived at read time from expires_at (spec.md section 5) - simulate
    # time having passed by moving expires_at into the past directly in the DB
    # (trigger disabled only for this test setup step, not for the assertion itself).
    await db_conn.execute(
        "ALTER TABLE mandate.mandates DISABLE TRIGGER trg_mandates_immutable"
    )
    try:
        await db_conn.execute(
            "UPDATE mandate.mandates SET expires_at = now() - interval '1 hour' WHERE mandate_id = $1",
            uuid.UUID(mandate_id),
        )
    finally:
        await db_conn.execute(
            "ALTER TABLE mandate.mandates ENABLE TRIGGER trg_mandates_immutable"
        )

    revoke = await client.post(
        f"/mandates/{mandate_id}/revoke",
        json={"reason_code": "BUYER_REQUEST"},
        headers={"Authorization": f"Bearer {buyer}"},
    )
    assert revoke.status_code == 200
    assert revoke.json() == {"status": "expired", "revoked": False}
