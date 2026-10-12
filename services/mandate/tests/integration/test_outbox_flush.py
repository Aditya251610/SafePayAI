"""Integration test for POST /internal/outbox/flush (sprint-plan S2-06): the shared relay
in libs/common/safepayai_common/outbox/relay.py, exercised against a real Postgres outbox
row and a deliberately unreachable audit URL -- proves the "audit down -> events retained,
not lost" requirement end to end (claim bumps attempts/next_attempt_at, nothing is marked
delivered, the row is still visible for the next flush).
"""

from __future__ import annotations

import json
import os
import uuid

import pytest


@pytest.fixture(autouse=True)
def _unreachable_audit(monkeypatch):
    # Port 1 is a reserved/unassigned port -- connection refused immediately, no real
    # network dependency or flakiness from an actual timeout.
    monkeypatch.setenv("PS_MANDATE_OUTBOX_RELAY_AUDIT_BASE_URL", "http://127.0.0.1:1")


async def test_flush_requires_tick_secret(client):
    resp = await client.post("/internal/outbox/flush")
    assert resp.status_code == 401


async def test_flush_leaves_row_pending_when_audit_unreachable(client, db_conn):
    event_id = str(uuid.uuid4())
    await db_conn.execute(
        """
        INSERT INTO mandate.outbox (event_id, type, version, aggregate_id, payload, trace_id)
        VALUES ($1, 'mandate.signed', 1, $2, $3::jsonb, $4)
        """,
        event_id,
        str(uuid.uuid4()),
        json.dumps({"hello": "world"}),
        str(uuid.uuid4()),
    )

    resp = await client.post(
        "/internal/outbox/flush",
        headers={"X-Tick-Secret": os.environ["INTERNAL_TICK_SECRET"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["delivered"] == 0
    assert body["failed"] >= 1
    assert body["pending"] >= 1

    row = await db_conn.fetchrow(
        "SELECT attempts, delivered_to, next_attempt_at FROM mandate.outbox WHERE event_id = $1",
        event_id,
    )
    assert row is not None
    assert row["attempts"] == 1
    assert row["delivered_to"] == "{}"
    assert row["next_attempt_at"] is not None


async def test_flush_is_a_noop_when_outbox_empty(client, db_conn):
    resp = await client.post(
        "/internal/outbox/flush",
        headers={"X-Tick-Secret": os.environ["INTERNAL_TICK_SECRET"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["delivered"] == 0
    assert body["pending"] == 0
