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
    proving the earlier 403 (for merchant) was a role decision, not a path/config
    coincidence. A real CSRF token is required too, now that CSRF is real."""
    await _login_operator(app_client, make_user)
    csrf_resp = await app_client.get("/api/auth/csrf")
    assert csrf_resp.status_code == 200
    token = csrf_resp.json()["csrf_token"]

    resp = await app_client.post(
        "/api/tracking/demo/clock/advance", headers={"X-CSRF-Token": token}
    )
    assert resp.status_code != 403


async def test_buyer_rejected_on_reviewer_only_route(app_client):
    await _login_buyer_via_demo_session(app_client)
    resp = await app_client.get("/api/resolution/review/queue")
    assert resp.status_code == 403
    assert resp.json()["error"] == "FORBIDDEN"


async def test_merchant_rejected_on_reviewer_only_route(app_client, make_user):
    await _login_merchant(app_client, make_user)
    resp = await app_client.get("/api/resolution/review/queue")
    assert resp.status_code == 403


async def test_reviewer_allowed_past_role_guard_on_review_queue(app_client, make_user):
    await make_user(
        handle="reviewer-role-test",
        role="reviewer",
        actor_type="reviewer",
        password_hash=hash_password("correct-password"),
    )
    resp = await app_client.post(
        "/api/auth/login",
        json={"handle": "reviewer-role-test", "password": "correct-password"},
    )
    assert resp.status_code == 200

    resp = await app_client.get("/api/resolution/review/queue")
    assert resp.status_code != 403


async def test_buyer_rejected_on_refunds_frozen_route(app_client):
    await _login_buyer_via_demo_session(app_client)
    resp = await app_client.get("/api/resolution/controls/refunds-frozen")
    assert resp.status_code == 403


async def test_buyer_allowed_past_role_guard_on_return_cancel_and_decline(app_client):
    """Buyer passes the role guard (require_buyer) on all three; each still needs its
    own CSRF token (single-use). What happens past that is upstream's concern (these
    hit a real FORBIDDEN only if the role guard itself rejected them)."""
    await _login_buyer_via_demo_session(app_client)
    tokens = [
        (await app_client.get("/api/auth/csrf")).json()["csrf_token"] for _ in range(3)
    ]

    return_resp = await app_client.post(
        "/api/checkout/orders/return",
        json={"state": "x", "token": "x", "payer_id": "x"},
        headers={"X-CSRF-Token": tokens[0]},
    )
    assert not (
        return_resp.status_code == 403 and return_resp.json()["error"] == "FORBIDDEN"
    )

    cancel_resp = await app_client.post(
        "/api/checkout/orders/cancel",
        json={"state": "x"},
        headers={"X-CSRF-Token": tokens[1]},
    )
    assert not (
        cancel_resp.status_code == 403 and cancel_resp.json()["error"] == "FORBIDDEN"
    )

    decline_resp = await app_client.post(
        "/api/resolution/offers/some-offer-id/decline",
        json={"reason_code": "NOT_WANTED"},
        headers={"X-CSRF-Token": tokens[2], "Idempotency-Key": "test-decline-1"},
    )
    assert not (
        decline_resp.status_code == 403 and decline_resp.json()["error"] == "FORBIDDEN"
    )


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
