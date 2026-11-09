"""POST /api/auth/signup against real Postgres (not run in the local sandbox; CI's
integration job provides the database)."""

from __future__ import annotations

from sqlalchemy import text


async def test_signup_creates_persistent_buyer_and_logs_in(app_client, db_engine):
    resp = await app_client.post(
        "/api/auth/signup",
        json={"handle": "Alice-One", "password": "correct-horse-1"},
    )
    assert resp.status_code == 201
    principal = resp.json()["principal"]
    assert principal["role"] == "buyer"
    assert principal["display_name"] == "alice-one"
    assert principal["merchant_id"] is None

    me = await app_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["actor_id"] == principal["actor_id"]

    async with db_engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT is_ephemeral, epoch, role, actor_type, password_hash "
                    'FROM "gateway"."users" WHERE handle = :h'
                ),
                {"h": "alice-one"},
            )
        ).first()
    assert row is not None
    assert row[0] is False and row[1] == 0
    assert row[2] == "buyer" and row[3] == "buyer"
    assert row[4].startswith("$argon2id$")


async def test_signup_then_login_roundtrip(app_client):
    await app_client.post(
        "/api/auth/signup", json={"handle": "bob-two", "password": "correct-horse-1"}
    )
    resp = await app_client.post(
        "/api/auth/login", json={"handle": "bob-two", "password": "correct-horse-1"}
    )
    assert resp.status_code == 200


async def test_signup_duplicate_handle_409(app_client):
    first = await app_client.post(
        "/api/auth/signup", json={"handle": "carol", "password": "correct-horse-1"}
    )
    assert first.status_code == 201
    second = await app_client.post(
        "/api/auth/signup", json={"handle": "CAROL", "password": "another-pass-22"}
    )
    assert second.status_code == 409
    assert second.json()["error"] == "HANDLE_TAKEN"


async def test_signup_reserved_handle_422(app_client):
    resp = await app_client.post(
        "/api/auth/signup",
        json={"handle": "merchant-evil", "password": "correct-horse-1"},
    )
    assert resp.status_code == 422
