"""Integration test for GET /internal/outbox (api.md section 7) -- previously a 501
stub. Exercises a real migrated Postgres agent.outbox table."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app_shopping_agent import deps


async def _fake_require_service_jwt() -> deps.ServicePrincipal:
    return deps.ServicePrincipal(sub="svc:audit", role="service", buyer_id=None)


@pytest.fixture(autouse=True)
def _patched_auth():
    from app_shopping_agent.main import app as fastapi_app

    fastapi_app.dependency_overrides[deps.require_service_jwt] = (
        _fake_require_service_jwt
    )
    yield
    fastapi_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_internal_outbox_returns_events_after_seq(client, db_engine) -> None:
    # No cross-test DB cleanup in this suite, so this anchors on the max seq already
    # present rather than assuming it starts at 0.
    async with db_engine.connect() as conn:
        baseline = (
            await conn.execute(text("SELECT COALESCE(MAX(seq), 0) FROM agent.outbox"))
        ).scalar_one()
        for _ in range(3):
            await conn.execute(
                text(
                    "INSERT INTO agent.outbox (event_id, type, version, aggregate_id, "
                    "payload, trace_id) VALUES (:event_id, 'cart.proposed', 1, "
                    ":aggregate_id, CAST(:payload AS jsonb), :trace_id)"
                ),
                {
                    "event_id": str(uuid.uuid4()),
                    "aggregate_id": str(uuid.uuid4()),
                    "payload": "{}",
                    "trace_id": str(uuid.uuid4()),
                },
            )
        await conn.commit()

    resp = await client.get(f"/internal/outbox?after={baseline}")
    assert resp.status_code == 200, resp.text
    events = resp.json()["events"]
    assert len(events) == 3

    resp2 = await client.get(f"/internal/outbox?after={events[0]['seq']}")
    assert resp2.status_code == 200
    assert len(resp2.json()["events"]) == 2


@pytest.mark.asyncio
async def test_internal_outbox_requires_auth(client, monkeypatch) -> None:
    from app_shopping_agent.main import app as fastapi_app

    fastapi_app.dependency_overrides.pop(deps.require_service_jwt, None)
    resp = await client.get("/internal/outbox")
    assert resp.status_code == 401
