"""Login/logout/session-expiry (task TESTS checklist item 1)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.auth.passwords import hash_password


async def test_demo_session_creates_buyer_and_sets_cookie(app_client):
    resp = await app_client.post("/api/auth/demo-session")
    assert resp.status_code == 201
    body = resp.json()
    assert body["principal"]["role"] == "buyer"
    assert body["principal"]["actor_type"] == "buyer"
    assert "__Host-ps_sid" in resp.cookies or any(
        c.name == "__Host-ps_sid" for c in app_client.cookies.jar
    )

    me = await app_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["role"] == "buyer"


async def test_login_success_then_me(app_client, make_user):
    await make_user(
        handle="merchant-1",
        role="merchant",
        actor_type="merchant_shared",
        display_name="Shared merchant (demo)",
        password_hash=hash_password("correct-password"),
    )

    resp = await app_client.post(
        "/api/auth/login", json={"handle": "merchant-1", "password": "correct-password"}
    )
    assert resp.status_code == 200
    assert resp.json()["principal"]["role"] == "merchant"

    me = await app_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["actor_type"] == "merchant_shared"


async def test_login_merchant_carries_merchant_id_through_session(
    app_client, make_user
):
    await make_user(
        handle="merchant-trailhead",
        role="merchant",
        actor_type="merchant",
        display_name="Trailhead (demo merchant)",
        password_hash=hash_password("correct-password"),
        merchant_id="mrc_trailhead",
    )

    resp = await app_client.post(
        "/api/auth/login",
        json={"handle": "merchant-trailhead", "password": "correct-password"},
    )
    assert resp.status_code == 200
    assert resp.json()["principal"]["merchant_id"] == "mrc_trailhead"

    me = await app_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["merchant_id"] == "mrc_trailhead"


async def test_login_non_merchant_has_null_merchant_id(app_client, make_user):
    await make_user(
        handle="operator-1",
        role="operator",
        actor_type="operator",
        display_name="Operator (demo)",
        password_hash=hash_password("correct-password"),
    )

    resp = await app_client.post(
        "/api/auth/login",
        json={"handle": "operator-1", "password": "correct-password"},
    )
    assert resp.status_code == 200
    assert resp.json()["principal"]["merchant_id"] is None


async def test_login_wrong_password_401(app_client, make_user):
    await make_user(
        handle="merchant-2",
        role="merchant",
        actor_type="merchant_shared",
        password_hash=hash_password("correct-password"),
    )
    resp = await app_client.post(
        "/api/auth/login", json={"handle": "merchant-2", "password": "wrong"}
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "UNAUTHENTICATED"


async def test_login_unknown_handle_401_same_error_as_wrong_password(
    app_client, make_user
):
    await make_user(
        handle="merchant-3",
        role="merchant",
        actor_type="merchant_shared",
        password_hash=hash_password("correct-password"),
    )
    wrong_password = await app_client.post(
        "/api/auth/login", json={"handle": "merchant-3", "password": "nope"}
    )
    unknown_handle = await app_client.post(
        "/api/auth/login", json={"handle": "no-such-handle", "password": "nope"}
    )
    assert wrong_password.status_code == unknown_handle.status_code == 401
    assert (
        wrong_password.json()["error"]
        == unknown_handle.json()["error"]
        == "UNAUTHENTICATED"
    )


async def test_logout_invalidates_session(app_client, make_user):
    await make_user(
        handle="merchant-4",
        role="merchant",
        actor_type="merchant_shared",
        password_hash=hash_password("correct-password"),
    )
    await app_client.post(
        "/api/auth/login", json={"handle": "merchant-4", "password": "correct-password"}
    )
    assert (await app_client.get("/api/auth/me")).status_code == 200

    logout_resp = await app_client.post("/api/auth/logout")
    assert logout_resp.status_code == 204

    me_after = await app_client.get("/api/auth/me")
    assert me_after.status_code == 401
    assert me_after.json()["error"] == "UNAUTHENTICATED"


async def test_session_expiry_enforced_server_side_not_just_cookie(
    app_client, make_user, db_engine
):
    """Even if the browser's cookie Max-Age hasn't elapsed, an `expires_at` in the
    past in the DB must be rejected (server-side enforcement, REQ-GW-003/U10)."""
    await make_user(
        handle="merchant-5",
        role="merchant",
        actor_type="merchant_shared",
        password_hash=hash_password("correct-password"),
    )
    await app_client.post(
        "/api/auth/login", json={"handle": "merchant-5", "password": "correct-password"}
    )
    assert (await app_client.get("/api/auth/me")).status_code == 200

    past = datetime.now(UTC) - timedelta(hours=1)
    async with db_engine.begin() as conn:
        await conn.execute(
            text('UPDATE "gateway"."sessions" SET expires_at = :past'), {"past": past}
        )

    me_after = await app_client.get("/api/auth/me")
    assert me_after.status_code == 401
    assert me_after.json()["error"] == "UNAUTHENTICATED"


async def test_epoch_bump_kills_session(app_client, make_user, db_engine):
    user = await make_user(
        handle="merchant-6",
        role="merchant",
        actor_type="merchant_shared",
        password_hash=hash_password("correct-password"),
    )
    await app_client.post(
        "/api/auth/login", json={"handle": "merchant-6", "password": "correct-password"}
    )
    assert (await app_client.get("/api/auth/me")).status_code == 200

    async with db_engine.begin() as conn:
        await conn.execute(
            text('UPDATE "gateway"."users" SET epoch = epoch + 1 WHERE id = :id'),
            {"id": user["id"]},
        )

    me_after = await app_client.get("/api/auth/me")
    assert me_after.status_code == 401
