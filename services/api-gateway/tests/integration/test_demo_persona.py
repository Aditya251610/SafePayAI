"""Demo-persona sign-in against real Postgres (CI integration job provides the DB)."""

from __future__ import annotations

import secrets

import pytest
from sqlalchemy import text


@pytest.fixture
def persona_flag(monkeypatch):
    monkeypatch.setenv("PS_APIGATEWAY_DEMO_PERSONA_LOGIN", "true")


async def test_flag_off_returns_404(app_client, make_user):
    await make_user(handle="operator", role="operator", actor_type="operator")
    assert (await app_client.get("/api/auth/demo-personas")).status_code == 404
    resp = await app_client.post("/api/auth/demo-persona", json={"handle": "operator"})
    assert resp.status_code == 404


async def test_persona_signin_then_me(app_client, make_user, persona_flag):
    await make_user(
        handle="merchant-trailhead",
        role="merchant",
        actor_type="merchant",
        display_name="Trailhead",
        merchant_id="mrc_trailhead",
    )
    listing = await app_client.get("/api/auth/demo-personas")
    assert listing.status_code == 200
    personas = listing.json()["personas"]
    assert [p["handle"] for p in personas] == ["merchant-trailhead"]
    assert set(personas[0]) == {"handle", "role", "display_name", "merchant_id"}

    resp = await app_client.post(
        "/api/auth/demo-persona", json={"handle": "merchant-trailhead"}
    )
    assert resp.status_code == 200
    assert resp.json()["principal"]["merchant_id"] == "mrc_trailhead"

    me = await app_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["role"] == "merchant"


async def test_signed_up_handle_is_refused(app_client, persona_flag):
    password = secrets.token_urlsafe(16)
    signup = await app_client.post(
        "/api/auth/signup", json={"handle": "carol-x", "password": password}
    )
    assert signup.status_code == 201
    app_client.cookies.clear()

    listing = await app_client.get("/api/auth/demo-personas")
    assert listing.json() == {"personas": []}
    resp = await app_client.post("/api/auth/demo-persona", json={"handle": "carol-x"})
    assert resp.status_code == 404
    assert (await app_client.get("/api/auth/me")).status_code == 401


async def test_disabled_persona_is_refused(
    app_client, db_engine, make_user, persona_flag
):
    await make_user(handle="operator", role="operator", actor_type="operator")
    async with db_engine.begin() as conn:
        await conn.execute(
            text(
                'UPDATE "gateway"."users" SET disabled_at = now() '
                "WHERE handle = 'operator'"
            )
        )
    resp = await app_client.post("/api/auth/demo-persona", json={"handle": "operator"})
    assert resp.status_code == 404
