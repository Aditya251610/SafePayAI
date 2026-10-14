"""/api/ops/* routes: status degrades to "unknown" rather than leaking an upstream
error/role rejection; freeze is operator+CSRF gated; tick needs a valid shared
secret. No real tracking/resolution/paypal-adapter instance runs in this test
env, so these exercise the gateway's own guard/degrade logic, not a live upstream
round-trip (same convention as the existing proxy role tests in test_roles.py)."""

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


async def test_ops_status_degrades_to_unknown_when_resolution_unreachable(
    app_client,
):
    await _login_buyer_via_demo_session(app_client)
    resp = await app_client.get("/api/ops/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["refunds_frozen"] == "unknown"
    assert "demo_mode" in body and "money_routes_enabled" in body and "build_id" in body


async def test_ops_status_requires_a_session(app_client):
    resp = await app_client.get("/api/ops/status")
    assert resp.status_code == 401


async def test_ops_freeze_rejects_merchant(app_client, make_user):
    await _login(
        app_client,
        make_user,
        handle="merchant-ops",
        role="merchant",
        actor_type="merchant",
    )
    resp = await app_client.post("/api/ops/freeze", json={"frozen": True})
    assert resp.status_code == 403


async def test_ops_freeze_rejects_missing_csrf(app_client, make_user):
    await _login(
        app_client,
        make_user,
        handle="operator-ops-1",
        role="operator",
        actor_type="operator",
    )
    resp = await app_client.post("/api/ops/freeze", json={"frozen": True})
    assert resp.status_code == 403


async def test_ops_freeze_passes_role_and_csrf_guards(app_client, make_user):
    await _login(
        app_client,
        make_user,
        handle="operator-ops-2",
        role="operator",
        actor_type="operator",
    )
    token = (await app_client.get("/api/auth/csrf?purpose=ops_freeze")).json()[
        "csrf_token"
    ]
    resp = await app_client.post(
        "/api/ops/freeze",
        json={"frozen": True, "reason": "test"},
        headers={"X-CSRF-Token": token},
    )
    # Past both guards; resolution isn't reachable in this test env, so the only
    # thing asserted is that neither guard itself rejected the call.
    assert resp.status_code != 403


async def test_ops_tick_rejects_missing_secret(app_client):
    resp = await app_client.post("/api/ops/tick")
    assert resp.status_code == 401


async def test_ops_tick_rejects_wrong_secret(app_client, monkeypatch):
    monkeypatch.setenv("PS_APIGATEWAY_TICK_SECRET", "real-secret")
    resp = await app_client.post(
        "/api/ops/tick", headers={"X-Tick-Secret": "wrong-secret"}
    )
    assert resp.status_code == 401


async def test_ops_tick_accepts_correct_secret(app_client, monkeypatch):
    monkeypatch.setenv("PS_APIGATEWAY_TICK_SECRET", "real-secret")
    resp = await app_client.post(
        "/api/ops/tick", headers={"X-Tick-Secret": "real-secret"}
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["detector"] == "unconfigured"
    assert body["reconcile"] == "unconfigured"
