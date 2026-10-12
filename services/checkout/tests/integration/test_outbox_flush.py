"""Integration test for POST /internal/outbox/flush (sprint-plan S2-06): the shared relay
in libs/common/safepayai_common/outbox/relay.py, exercised against a real Postgres outbox
row and a deliberately unreachable audit URL -- proves the "audit down -> events retained,
not lost" requirement end to end.

checkout/app/routers/internal.py uses `_require_tick_secret` for this endpoint specifically
(the INTERNAL_TICK_SECRET bare-name cron convention, not `require_service_jwt`'s live-JWKS
check -- see that module's docstring), so this test does not need the
`require_service_jwt` dependency override the other checkout integration tests use.
"""

from __future__ import annotations

import json
import os
import uuid

import pytest


@pytest.fixture(autouse=True)
def _flush_env(monkeypatch):
    # Port 1 is reserved/unassigned -- connection refused immediately, no real network
    # dependency or timeout flakiness.
    monkeypatch.setenv("PS_CHECKOUT_OUTBOX_RELAY_AUDIT_BASE_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("INTERNAL_TICK_SECRET", "test-tick-secret")


async def test_flush_requires_tick_secret(client):
    resp = await client.post("/internal/outbox/flush")
    assert resp.status_code == 401


async def test_flush_leaves_row_pending_when_audit_unreachable(client, db_engine):
    event_id = str(uuid.uuid4())
    aggregate_id = str(uuid.uuid4())
    async with db_engine.connect() as conn:
        from sqlalchemy import text

        await conn.execute(
            text(
                "INSERT INTO checkout.outbox (event_id, type, version, aggregate_id, "
                "payload, trace_id) VALUES (:event_id, 'cart.created', 1, :aggregate_id, "
                "CAST(:payload AS jsonb), :trace_id)"
            ),
            {
                "event_id": event_id,
                "aggregate_id": aggregate_id,
                "payload": json.dumps({"hello": "world"}),
                "trace_id": str(uuid.uuid4()),
            },
        )
        await conn.commit()

    resp = await client.post(
        "/internal/outbox/flush",
        headers={"X-Tick-Secret": os.environ["INTERNAL_TICK_SECRET"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["delivered"] == 0
    assert body["failed"] >= 1
    assert body["pending"] >= 1

    async with db_engine.connect() as conn:
        from sqlalchemy import text

        row = (
            (
                await conn.execute(
                    text(
                        "SELECT attempts, delivered_to, next_attempt_at FROM checkout.outbox "
                        "WHERE event_id = :event_id"
                    ),
                    {"event_id": event_id},
                )
            )
            .mappings()
            .first()
        )
    assert row is not None
    assert row["attempts"] == 1
    assert row["delivered_to"] == {}
    assert row["next_attempt_at"] is not None
