"""Real CSRF implementation (app/csrf.py): single-use, purpose-scoped, session-bound
tokens backed by `gateway.csrf_uses`. GET /api/auth/csrf issues a token; every
state-changing proxy route consumes one via require_csrf()."""

from __future__ import annotations

from app.auth.passwords import hash_password


async def _login_buyer(app_client):
    resp = await app_client.post("/api/auth/demo-session")
    assert resp.status_code == 201


async def _login_merchant(app_client, make_user, handle="csrf-merchant"):
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


async def test_csrf_requires_a_session(app_client):
    resp = await app_client.get("/api/auth/csrf")
    assert resp.status_code == 401


async def test_csrf_issues_a_token_bound_to_the_session(app_client):
    await _login_buyer(app_client)
    resp = await app_client.get("/api/auth/csrf")
    assert resp.status_code == 200
    body = resp.json()
    assert body["purpose"] == "general"
    assert len(body["csrf_token"]) > 0
    assert "expires_at" in body


async def test_state_changing_route_rejects_missing_csrf_token(app_client):
    await _login_buyer(app_client)
    resp = await app_client.post("/api/mandate/mandates", json={"terms": {}})
    assert resp.status_code == 403
    assert resp.json()["error"] == "CSRF_INVALID"


async def test_state_changing_route_rejects_garbage_csrf_token(app_client):
    await _login_buyer(app_client)
    resp = await app_client.post(
        "/api/mandate/mandates",
        json={"terms": {}},
        headers={"X-CSRF-Token": "not-a-real-token"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "CSRF_INVALID"


async def test_csrf_token_is_single_use(app_client):
    await _login_buyer(app_client)
    token = (await app_client.get("/api/auth/csrf")).json()["csrf_token"]

    first = await app_client.post(
        "/api/mandate/mandates", json={"terms": {}}, headers={"X-CSRF-Token": token}
    )
    # Whatever mandate does with a malformed body is irrelevant here -- the point is
    # the CSRF check itself passed (not a 403), proving the token was accepted once.
    assert first.status_code != 403

    replay = await app_client.post(
        "/api/mandate/mandates", json={"terms": {}}, headers={"X-CSRF-Token": token}
    )
    assert replay.status_code == 403
    assert replay.json()["error"] == "CSRF_INVALID"


async def test_csrf_token_cannot_be_used_by_a_different_session(app_client, make_user):
    await _login_buyer(app_client)
    token = (await app_client.get("/api/auth/csrf")).json()["csrf_token"]

    # Log out of the buyer session and log in as someone else -- a different session,
    # different sid_hash, same browser/client (cookie jar swapped, not a new attacker,
    # but the token's binding check is what's under test here either way).
    await app_client.post("/api/auth/logout")
    await _login_merchant(app_client, make_user)

    resp = await app_client.post(
        "/api/tracking/shipments",
        json={},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "CSRF_INVALID"


async def test_login_and_demo_session_and_logout_do_not_need_csrf(
    app_client, make_user
):
    # These are the deliberate exemptions (app/csrf.py's own docstring): no session
    # exists yet for login/demo-session, and logout isn't a meaningful CSRF target.
    demo_resp = await app_client.post("/api/auth/demo-session")
    assert demo_resp.status_code == 201

    logout_resp = await app_client.post("/api/auth/logout")
    assert logout_resp.status_code == 204

    await make_user(
        handle="csrf-noexempt",
        role="merchant",
        actor_type="merchant_shared",
        password_hash=hash_password("correct-password"),
    )
    login_resp = await app_client.post(
        "/api/auth/login",
        json={"handle": "csrf-noexempt", "password": "correct-password"},
    )
    assert login_resp.status_code == 200
