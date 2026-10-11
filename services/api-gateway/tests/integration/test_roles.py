"""Role-based route guards (task TESTS checklist item 2): buyer rejected on
merchant-only routes and vice versa; anon rejected everywhere protected."""

from __future__ import annotations

from app.auth.passwords import hash_password


async def _login_buyer_via_demo_session(app_client):
    resp = await app_client.post("/api/auth/demo-session")
    assert resp.status_code == 201


async def _login_merchant(app_client, make_user, handle="merchant-role-test"):
    await make_user(
        handle=handle,
        role="merchant",
        actor_type="merchant_shared",
        password_hash=hash_password("correct-password"),
    )
    resp = await app_client.post(
        "/api/auth/login", json={"handle": handle, "password": "correct-password"}
    )
    assert resp.status_code == 200


async def _login_operator(app_client, make_user, handle="operator-role-test"):
    await make_user(
        handle=handle,
        role="operator",
        actor_type="operator",
        password_hash=hash_password("correct-password"),
    )
    resp = await app_client.post(
        "/api/auth/login", json={"handle": handle, "password": "correct-password"}
    )
    assert resp.status_code == 200


async def test_buyer_rejected_on_merchant_only_route(app_client):
    await _login_buyer_via_demo_session(app_client)
    # POST /api/tracking/shipments is merchant-only (api.md section 4).
    resp = await app_client.post("/api/tracking/shipments", json={})
    assert resp.status_code == 403
    assert resp.json()["error"] == "FORBIDDEN"


async def test_merchant_rejected_on_buyer_only_route(app_client, make_user):
    await _login_merchant(app_client, make_user)
    # POST /api/mandate/mandates is buyer-only (api.md section 4).
    resp = await app_client.post("/api/mandate/mandates", json={})
    assert resp.status_code == 403
    assert resp.json()["error"] == "FORBIDDEN"


async def test_buyer_rejected_on_operator_only_route(app_client):
    await _login_buyer_via_demo_session(app_client)
    resp = await app_client.post("/api/ops/freeze", json={"frozen": True})
    assert resp.status_code == 403


async def test_merchant_rejected_on_operator_only_demo_route(app_client, make_user):
    await _login_merchant(app_client, make_user)
    resp = await app_client.post("/api/tracking/demo/clock/advance")
    assert resp.status_code == 403


async def test_operator_allowed_past_role_guard_on_demo_route(app_client, make_user):
    """Operator passes the role guard; it then hits the (expected, since no
    tracking upstream is configured in this test env) 503 from the proxy layer -
    proving the 403 above was a role decision, not a path/config coincidence."""
    await _login_operator(app_client, make_user)
    resp = await app_client.post("/api/tracking/demo/clock/advance")
    assert resp.status_code != 403


async def test_anon_rejected_on_protected_routes(app_client):
    for method, path in [
        ("GET", "/api/auth/me"),
        ("GET", "/api/catalog/items"),
        ("POST", "/api/mandate/mandates"),
        ("GET", "/api/ops/status"),
    ]:
        resp = await app_client.request(method, path)
        assert resp.status_code == 401, f"{method} {path} should be 401 for anon"
        assert resp.json()["error"] == "UNAUTHENTICATED"


async def test_unknown_path_is_404_default_deny(app_client):
    resp = await app_client.get("/api/this-route-does-not-exist")
    assert resp.status_code == 404


async def test_internal_path_is_404(app_client):
    resp = await app_client.get("/internal/anything")
    assert resp.status_code == 404
