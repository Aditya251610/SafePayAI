"""Proxy routes forward the request body (and the new resolution routes exist with
the right roles). `forward` is stubbed; session/CSRF dependencies are overridden."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.db import get_db_session
from app.deps import Principal, require_session


def _principal(role: str) -> Principal:
    return Principal(actor_type=role, actor_id="u-1", role=role, epoch=0, sid_hash="h")


@pytest.fixture
def harness(monkeypatch):
    from app.main import app
    from app.routers import proxy as proxy_router

    calls: list[dict] = []

    async def _fake_forward(request, response, **kwargs):
        calls.append(kwargs)
        return {"ok": True}

    monkeypatch.setattr(proxy_router, "forward", _fake_forward)

    class _Mappings:
        def mappings(self):
            return self

        def first(self):
            # A valid, unexpired CSRF row bound to the stubbed principal's sid_hash.
            return {
                "sid_hash": "h",
                "purpose": "general",
                "expires_at": datetime.now(UTC) + timedelta(minutes=5),
            }

    class _FakeDb:
        async def execute(self, *_a, **_k):
            return _Mappings()

        async def commit(self):
            return None

    async def _db():
        return _FakeDb()

    app.dependency_overrides[get_db_session] = _db

    def _client(role: str) -> TestClient:
        app.dependency_overrides[require_session] = lambda: _principal(role)
        return TestClient(app, headers={"X-CSRF-Token": str(uuid.uuid4())})

    yield _client, calls
    app.dependency_overrides.clear()


CASES = [
    ("buyer", "/api/mandate/mandates/m-1/revoke", "/mandates/m-1/revoke", "mandate"),
    ("buyer", "/api/resolution/offers/o-1/accept", "/offers/o-1/accept", "resolution"),
    (
        "buyer",
        "/api/resolution/approvals/tok/consent",
        "/approvals/tok/consent",
        "resolution",
    ),
    (
        "operator",
        "/api/tracking/demo/shipments/s-1/force",
        "/demo/shipments/s-1/force",
        "tracking",
    ),
    (
        "reviewer",
        "/api/resolution/cases/c-1/review-decision",
        "/cases/c-1/review-decision",
        "resolution",
    ),
    ("buyer", "/api/resolution/cases/c-1/appeal", "/cases/c-1/appeal", "resolution"),
]


@pytest.mark.parametrize(("role", "path", "upstream", "service"), CASES)
def test_body_reaches_forward(harness, role, path, upstream, service):
    client_for, calls = harness
    payload = {"proposal_hash": "abc", "reason": "because"}
    resp = client_for(role).post(path, json=payload)
    assert resp.status_code == 200
    assert calls[-1]["body"] == payload
    assert calls[-1]["upstream_path"] == upstream
    assert calls[-1]["service"] == service


@pytest.mark.parametrize(("role", "path", "upstream", "service"), CASES)
def test_missing_body_defaults_to_empty_dict(harness, role, path, upstream, service):
    client_for, calls = harness
    assert client_for(role).post(path).status_code == 200
    assert calls[-1]["body"] == {}


@pytest.mark.parametrize(
    ("path", "wrong_role"),
    [
        ("/api/resolution/cases/c-1/review-decision", "buyer"),
        ("/api/resolution/cases/c-1/appeal", "reviewer"),
    ],
)
def test_new_routes_enforce_roles(harness, path, wrong_role):
    client_for, calls = harness
    assert client_for(wrong_role).post(path, json={}).status_code == 403
    assert calls == []


def test_notifications_buyer_only_get(harness):
    client_for, calls = harness
    assert client_for("buyer").get("/api/resolution/notifications").status_code == 200
    assert calls[-1]["upstream_path"] == "/notifications"
    assert calls[-1]["method"] == "GET"
    assert (
        client_for("reviewer").get("/api/resolution/notifications").status_code == 403
    )


def test_idempotency_flags_unchanged_for_money_routes(harness):
    client_for, calls = harness
    client_for("buyer").post("/api/resolution/offers/o-1/accept", json={})
    assert calls[-1]["require_idempotency"] is True
    assert calls[-1]["money_route"] is True
