"""/api/bff/* aggregators. No real checkout/tracking/resolution/audit instance
runs in this test env, so order_detail's checkout leg always misses -> 404; this
exercises the gateway's own role guard and degrade-to-partial logic (same
convention as test_ops.py), not a live upstream round-trip."""

from __future__ import annotations

from app.auth.passwords import hash_password


async def _login_buyer_via_demo_session(app_client):
    resp = await app_client.post("/api/auth/demo-session")
    assert resp.status_code == 201


async def _login(app_client, make_user, *, handle, role, actor_type):
    await make_user(
        handle=handle,
        role=role,
        actor_type=actor_type,
        password_hash=hash_password("correct-password"),
    )
    resp = await app_client.post(
        "/api/auth/login", json={"handle": handle, "password": "correct-password"}
    )
    assert resp.status_code == 200


async def test_buyer_home_requires_buyer_role(app_client, make_user):
    await _login(
        app_client,
        make_user,
        handle="merchant-buyer-home",
        role="merchant",
        actor_type="merchant",
    )
    resp = await app_client.get("/api/bff/buyer-home")
    assert resp.status_code == 403


async def test_buyer_home_degrades_to_nulls_when_upstreams_unreachable(app_client):
    await _login_buyer_via_demo_session(app_client)
    resp = await app_client.get("/api/bff/buyer-home")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mandates"] == []
    assert body["latest_order"] is None
    assert body["active_case"] is None


async def test_order_detail_requires_buyer_role(app_client, make_user):
    await _login(
        app_client,
        make_user,
        handle="merchant-bff",
        role="merchant",
        actor_type="merchant",
    )
    resp = await app_client.get("/api/bff/orders/some-order")
    assert resp.status_code == 403


async def test_order_detail_404s_when_checkout_unreachable(app_client):
    await _login_buyer_via_demo_session(app_client)
    resp = await app_client.get("/api/bff/orders/some-order")
    assert resp.status_code == 404
    assert resp.json()["error"] == "ORDER_NOT_FOUND"


async def test_merchant_queue_requires_staff_role(app_client):
    await _login_buyer_via_demo_session(app_client)
    resp = await app_client.get("/api/bff/merchant-queue")
    assert resp.status_code == 403


async def test_merchant_queue_degrades_to_empty_when_resolution_unreachable(
    app_client, make_user
):
    await _login(
        app_client,
        make_user,
        handle="operator-bff",
        role="operator",
        actor_type="operator",
    )
    resp = await app_client.get("/api/bff/merchant-queue")
    assert resp.status_code == 200
    body = resp.json()
    assert body["cases"] == []
    assert body["tracking_pending"] is None
