"""Demo-persona sign-in: flag gate, allowlist, shape, rate limit (fake DB, no Postgres)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

USER_ID = "22222222-2222-2222-2222-222222222222"
ROW = {
    "id": USER_ID,
    "role": "merchant",
    "actor_type": "merchant",
    "display_name": "Trailhead",
    "epoch": 3,
    "merchant_id": "mrc_trailhead",
}


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.executed: list[dict] = []

    async def execute(self, _stmt, params=None):
        self.executed.append(params or {})
        return _Result(self.rows)

    async def commit(self):
        pass


@pytest.fixture
def make_client(monkeypatch):
    from app.db import get_db_session
    from app.main import app
    from app.ratelimit import limiter
    from app.routers import auth as auth_router

    limiter.reset()
    created: list[dict] = []

    async def _fake_create_session(db, *, user_id, role, epoch, settings):
        created.append({"user_id": user_id, "role": role, "epoch": epoch})
        return "raw-sid", datetime.now(UTC) + timedelta(hours=1)

    monkeypatch.setattr(auth_router, "create_session", _fake_create_session)

    def _make(rows, flag=True):
        monkeypatch.setenv(
            "PS_APIGATEWAY_DEMO_PERSONA_LOGIN", "true" if flag else "false"
        )
        fake = _FakeSession(rows)

        async def _override():
            return fake

        app.dependency_overrides[get_db_session] = _override
        return TestClient(app, base_url="https://testserver"), fake, created

    yield _make
    app.dependency_overrides.clear()
    limiter.reset()


def test_flag_off_404_both_routes(make_client):
    client, fake, created = make_client([ROW], flag=False)
    r1 = client.get("/api/auth/demo-personas")
    r2 = client.post("/api/auth/demo-persona", json={"handle": "operator"})
    assert r1.status_code == r2.status_code == 404
    assert r1.json()["error"] == r2.json()["error"] == "NOT_FOUND"
    assert fake.executed == [] and created == []


def test_flag_defaults_off(monkeypatch):
    monkeypatch.delenv("PS_APIGATEWAY_DEMO_PERSONA_LOGIN", raising=False)
    from app.settings import Settings

    assert Settings().demo_persona_login is False


def test_list_only_exposes_allowlisted_fields(make_client):
    rows = [
        {
            "handle": "merchant-trailhead",
            "role": "merchant",
            "display_name": "Trailhead",
            "merchant_id": "mrc_trailhead",
            "password_hash": "x",
            "id": "y",
        }
    ]
    client, fake, _ = make_client(rows)
    resp = client.get("/api/auth/demo-personas")
    assert resp.status_code == 200
    assert resp.json() == {
        "personas": [
            {
                "handle": "merchant-trailhead",
                "role": "merchant",
                "display_name": "Trailhead",
                "merchant_id": "mrc_trailhead",
            }
        ]
    }
    from app.routers.auth import DEMO_PERSONA_HANDLES

    assert fake.executed[0]["handles"] == list(DEMO_PERSONA_HANDLES)


def test_allowlist_is_exact():
    from app.routers.auth import DEMO_PERSONA_HANDLES

    assert set(DEMO_PERSONA_HANDLES) == {
        "buyer-persona",
        "buyer-alex",
        "reviewer-demo",
        "operator",
        "merchant-trailhead",
        "merchant-hearth",
        "merchant-pixelwire",
    }


def test_signin_success_shape_and_cookie(make_client):
    client, _, created = make_client([ROW])
    resp = client.post("/api/auth/demo-persona", json={"handle": "merchant-trailhead"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["principal"] == {
        "actor_type": "merchant",
        "actor_id": USER_ID,
        "role": "merchant",
        "display_name": "Trailhead",
        "merchant_id": "mrc_trailhead",
    }
    assert "expires_at" in body
    assert "__Host-ps_sid=raw-sid" in resp.headers["set-cookie"]
    assert created == [{"user_id": USER_ID, "role": "merchant", "epoch": 3}]


@pytest.mark.parametrize("handle", ["alice", "buyer-persona2", "Operator", "nobody"])
def test_non_allowlisted_is_404_without_db_or_session(make_client, handle):
    client, fake, created = make_client([ROW])
    resp = client.post("/api/auth/demo-persona", json={"handle": handle})
    assert resp.status_code == 404
    assert resp.json()["error"] == "NOT_FOUND"
    assert fake.executed == [] and created == []
    assert "set-cookie" not in resp.headers


def test_allowlisted_but_missing_is_same_404(make_client):
    client, _, created = make_client([])
    resp = client.post("/api/auth/demo-persona", json={"handle": "operator"})
    unknown = client.post("/api/auth/demo-persona", json={"handle": "nobody"})
    assert resp.status_code == 404 and created == []
    assert resp.json()["error"] == unknown.json()["error"]
    assert resp.json()["message"] == unknown.json()["message"]


def test_extra_fields_forbidden(make_client):
    client, _, _ = make_client([ROW])
    resp = client.post(
        "/api/auth/demo-persona", json={"handle": "operator", "role": "buyer"}
    )
    assert resp.status_code == 422


def test_rate_limited_per_ip(make_client):
    from app.routers.auth import AUTH_PERSONA_RATE_LIMIT

    client, _, _ = make_client([ROW])
    for _ in range(AUTH_PERSONA_RATE_LIMIT):
        status = client.post("/api/auth/demo-persona", json={"handle": "operator"})
        assert status.status_code == 200
    resp = client.post("/api/auth/demo-persona", json={"handle": "operator"})
    assert resp.status_code == 429
    assert resp.json()["error"] == "RATE_LIMITED"
