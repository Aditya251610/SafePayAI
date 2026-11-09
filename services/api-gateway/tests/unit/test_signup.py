"""POST /api/auth/signup: schema validation + handler behaviour with a fake DB
session (no Postgres needed)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.schemas.auth import SignupRequest

USER_ID = "11111111-1111-1111-1111-111111111111"


class _Result:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _FakeSession:
    def __init__(self, row):
        self.row = row
        self.executed: list[dict] = []
        self.commits = 0

    async def execute(self, _stmt, params=None):
        self.executed.append(params or {})
        return _Result(self.row)

    async def commit(self):
        self.commits += 1


@pytest.fixture
def client_factory(monkeypatch):
    from app.db import get_db_session
    from app.main import app
    from app.routers import auth as auth_router

    created: list[dict] = []

    async def _fake_create_session(db, *, user_id, role, epoch, settings):
        created.append({"user_id": user_id, "role": role, "epoch": epoch})
        return "raw-sid", datetime.now(UTC) + timedelta(hours=2)

    monkeypatch.setattr(auth_router, "create_session", _fake_create_session)

    def _make(row):
        fake = _FakeSession(row)

        async def _override():
            return fake

        app.dependency_overrides[get_db_session] = _override
        return TestClient(app, base_url="https://testserver"), fake, created

    yield _make
    app.dependency_overrides.clear()


# ---- schema -----------------------------------------------------------------


def test_handle_is_stripped_and_lowercased():
    req = SignupRequest(handle="  Alice_01 ", password="correct-horse-1")
    assert req.handle == "alice_01"
    assert req.display_name is None


@pytest.mark.parametrize(
    "handle",
    [
        "ab",
        "-abc",
        "a" * 33,
        "has space",
        "bad!char",
        "merchant-foo",
        "operator1",
        "reviewer-x",
        "admin",
        "demo-user",
        "buyer-persona2",
    ],
)
def test_bad_or_reserved_handles_rejected(handle):
    with pytest.raises(ValidationError):
        SignupRequest(handle=handle, password="correct-horse-1")


@pytest.mark.parametrize("password", ["short", "x" * 9, "x" * 129])
def test_password_length_bounds(password):
    with pytest.raises(ValidationError):
        SignupRequest(handle="alice", password=password)


def test_display_name_bounds_and_extra_forbidden():
    with pytest.raises(ValidationError):
        SignupRequest(handle="alice", password="correct-horse-1", display_name="")
    with pytest.raises(ValidationError):
        SignupRequest(handle="alice", password="correct-horse-1", display_name="x" * 61)
    with pytest.raises(ValidationError):
        SignupRequest(handle="alice", password="correct-horse-1", role="operator")


def test_password_not_in_repr():
    assert "correct-horse-1" not in repr(
        SignupRequest(handle="alice", password="correct-horse-1")
    )


# ---- handler ----------------------------------------------------------------


def test_signup_success_creates_persistent_buyer_and_session(client_factory):
    client, fake, created = client_factory((USER_ID, 0))
    resp = client.post(
        "/api/auth/signup", json={"handle": "Alice", "password": "correct-horse-1"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["principal"] == {
        "actor_type": "buyer",
        "actor_id": USER_ID,
        "role": "buyer",
        "display_name": "alice",
        "merchant_id": None,
    }
    assert "expires_at" in body
    assert "__Host-ps_sid=raw-sid" in resp.headers["set-cookie"]
    params = fake.executed[0]
    assert params["handle"] == "alice"
    assert params["password_hash"].startswith("$argon2id$")
    assert "correct-horse-1" not in params["password_hash"]
    assert created == [{"user_id": USER_ID, "role": "buyer", "epoch": 0}]


def test_signup_uses_custom_display_name(client_factory):
    client, _, _ = client_factory((USER_ID, 0))
    resp = client.post(
        "/api/auth/signup",
        json={
            "handle": "alice",
            "password": "correct-horse-1",
            "display_name": "Alice A.",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["principal"]["display_name"] == "Alice A."


def test_signup_duplicate_handle_is_409_without_session(client_factory):
    client, _, created = client_factory(None)  # ON CONFLICT DO NOTHING -> no row
    resp = client.post(
        "/api/auth/signup", json={"handle": "alice", "password": "correct-horse-1"}
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"] == "HANDLE_TAKEN"
    assert body["message"] and body["request_id"]
    assert "set-cookie" not in resp.headers
    assert created == []


def test_signup_invalid_input_is_422(client_factory):
    client, fake, _ = client_factory(None)
    resp = client.post(
        "/api/auth/signup", json={"handle": "admin", "password": "correct-horse-1"}
    )
    assert resp.status_code == 422
    assert fake.executed == []


def test_signup_rate_limited_per_ip(client_factory):
    from app.routers.auth import AUTH_SIGNUP_RATE_LIMIT

    client, _, _ = client_factory((USER_ID, 0))
    for _ in range(AUTH_SIGNUP_RATE_LIMIT):
        assert (
            client.post(
                "/api/auth/signup",
                json={"handle": "alice", "password": "correct-horse-1"},
            ).status_code
            == 201
        )
    resp = client.post(
        "/api/auth/signup", json={"handle": "alice", "password": "correct-horse-1"}
    )
    assert resp.status_code == 429
    assert resp.json()["error"] == "RATE_LIMITED"
