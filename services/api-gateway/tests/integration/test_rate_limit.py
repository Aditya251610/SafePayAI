"""Rate limiting on auth endpoints (task TESTS checklist item 3): the Nth login
attempt in a window gets 429 with Retry-After."""

from __future__ import annotations

from app.auth.passwords import hash_password
from app.routers.auth import AUTH_LOGIN_RATE_LIMIT


async def test_nth_login_attempt_in_window_gets_429(app_client, make_user):
    await make_user(
        handle="rl-target",
        role="merchant",
        actor_type="merchant_shared",
        password_hash=hash_password("correct-password"),
    )

    last_resp = None
    for _ in range(AUTH_LOGIN_RATE_LIMIT):
        last_resp = await app_client.post(
            "/api/auth/login", json={"handle": "rl-target", "password": "wrong"}
        )
        assert last_resp.status_code == 401

    throttled = await app_client.post(
        "/api/auth/login", json={"handle": "rl-target", "password": "wrong"}
    )
    assert throttled.status_code == 429
    assert throttled.json()["error"] == "RATE_LIMITED"
    assert "Retry-After" in throttled.headers


async def test_rate_limit_is_keyed_by_ip_and_handle_not_global(app_client, make_user):
    """A different handle from the same test client (same IP, per ASGITransport's
    fixed client address) must not be blocked by another handle's limit."""
    await make_user(
        handle="rl-target-a",
        role="merchant",
        actor_type="merchant_shared",
        password_hash=hash_password("correct-password"),
    )
    await make_user(
        handle="rl-target-b",
        role="merchant",
        actor_type="merchant_shared",
        password_hash=hash_password("correct-password"),
    )

    for _ in range(AUTH_LOGIN_RATE_LIMIT):
        await app_client.post(
            "/api/auth/login", json={"handle": "rl-target-a", "password": "wrong"}
        )

    still_allowed = await app_client.post(
        "/api/auth/login", json={"handle": "rl-target-b", "password": "correct-password"}
    )
    assert still_allowed.status_code == 200
