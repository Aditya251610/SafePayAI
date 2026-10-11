"""Preview -> sign -> read lifecycle; idempotency; nonce replay; tamper/integrity."""

from __future__ import annotations

import uuid

from tests.integration.helpers import preview_and_sign, sample_terms


async def test_preview_then_sign_success(client, buyer_token):
    token = buyer_token()
    mandate = await preview_and_sign(client, token, str(uuid.uuid4()))
    assert mandate["status"] == "active"
    assert mandate["integrity"] == "OK"
    assert mandate["spent_minor"] == 0
    assert mandate["remaining_minor"] == 6000


async def test_sign_rejects_body_screen_text_mismatch(client, buyer_token):
    token = buyer_token()
    headers = {"Authorization": f"Bearer {token}"}
    preview_resp = await client.post(
        "/mandates/preview", json={"terms": sample_terms()}, headers=headers
    )
    preview = preview_resp.json()

    resp = await client.post(
        "/mandates",
        json={
            "terms": sample_terms(),
            "screen_text_hash": "0" * 64,
            "nonce": preview["nonce"],
        },
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "SCREEN_TEXT_MISMATCH"


async def test_idempotent_replay_same_key_same_body(client, buyer_token):
    token = buyer_token()
    headers = {"Authorization": f"Bearer {token}"}
    preview_resp = await client.post(
        "/mandates/preview", json={"terms": sample_terms()}, headers=headers
    )
    preview = preview_resp.json()
    key = str(uuid.uuid4())
    body = {
        "terms": sample_terms(),
        "screen_text_hash": preview["screen_text_hash"],
        "nonce": preview["nonce"],
    }

    first = await client.post(
        "/mandates", json=body, headers={**headers, "Idempotency-Key": key}
    )
    assert first.status_code == 201
    assert "Idempotent-Replay" not in first.headers

    second = await client.post(
        "/mandates", json=body, headers={**headers, "Idempotency-Key": key}
    )
    assert second.status_code == 201
    assert second.headers.get("Idempotent-Replay") == "true"
    assert second.json()["mandate_id"] == first.json()["mandate_id"]


async def test_idempotency_key_reused_with_different_body_is_409(client, buyer_token):
    token = buyer_token()
    headers = {"Authorization": f"Bearer {token}"}
    key = str(uuid.uuid4())

    preview1 = (
        await client.post(
            "/mandates/preview", json={"terms": sample_terms()}, headers=headers
        )
    ).json()
    first = await client.post(
        "/mandates",
        json={
            "terms": sample_terms(),
            "screen_text_hash": preview1["screen_text_hash"],
            "nonce": preview1["nonce"],
        },
        headers={**headers, "Idempotency-Key": key},
    )
    assert first.status_code == 201

    preview2 = (
        await client.post(
            "/mandates/preview",
            json={"terms": sample_terms(max_total_minor=7000)},
            headers=headers,
        )
    ).json()
    second = await client.post(
        "/mandates",
        json={
            "terms": sample_terms(max_total_minor=7000),
            "screen_text_hash": preview2["screen_text_hash"],
            "nonce": preview2["nonce"],
        },
        headers={**headers, "Idempotency-Key": key},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


async def test_nonce_replay_is_rejected(client, buyer_token):
    token = buyer_token()
    headers = {"Authorization": f"Bearer {token}"}
    preview = (
        await client.post(
            "/mandates/preview", json={"terms": sample_terms()}, headers=headers
        )
    ).json()
    body = {
        "terms": sample_terms(),
        "screen_text_hash": preview["screen_text_hash"],
        "nonce": preview["nonce"],
    }

    first = await client.post(
        "/mandates",
        json=body,
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert first.status_code == 201

    # Same nonce, different idempotency key -> forces past the idempotency lookup
    # into the nonce check, which must reject the already-burnt nonce.
    second = await client.post(
        "/mandates",
        json=body,
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "NONCE_INVALID"


async def test_mandate_not_found_for_wrong_owner(client, buyer_token):
    owner_token = buyer_token("buyer-owner")
    other_token = buyer_token("buyer-other")
    mandate = await preview_and_sign(client, owner_token, str(uuid.uuid4()))

    resp = await client.get(
        f"/mandates/{mandate['mandate_id']}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "MANDATE_NOT_FOUND"


async def test_merchant_view_is_minimal(client, buyer_token, merchant_token):
    mandate = await preview_and_sign(client, buyer_token(), str(uuid.uuid4()))
    resp = await client.get(
        f"/mandates/{mandate['mandate_id']}",
        headers={"Authorization": f"Bearer {merchant_token()}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "intent_text" not in body
    assert "buyer_id" not in body
    assert "spent_minor" not in body


async def test_verify_detects_tamper(client, buyer_token, db_conn):
    mandate = await preview_and_sign(client, buyer_token(), str(uuid.uuid4()))
    # The row is immutable by trigger even for the superuser; disable it just for
    # this simulated post-hoc tamper, as the attack model in spec.md section 15
    # assumes (DB owner access, not the runtime svc_mandate role).
    await db_conn.execute(
        "ALTER TABLE mandate.mandates DISABLE TRIGGER trg_mandates_immutable"
    )
    try:
        await db_conn.execute(
            "UPDATE mandate.mandates SET intent_text = 'tampered' WHERE mandate_id = $1",
            uuid.UUID(mandate["mandate_id"]),
        )
    finally:
        await db_conn.execute(
            "ALTER TABLE mandate.mandates ENABLE TRIGGER trg_mandates_immutable"
        )
    resp = await client.get(
        f"/mandates/{mandate['mandate_id']}/verify",
        headers={"Authorization": f"Bearer {buyer_token()}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["integrity"] == "FAILED"
    assert body["checks"]["canonical_matches"] is False
