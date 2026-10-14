"""Integration test for POST /internal/outbox/flush (sprint-plan S2-06): the shared relay
in libs/common/safepayai_common/outbox/relay.py, exercised against a real Postgres
`paypal.outbox` row and a deliberately unreachable audit URL.

Previously untested end to end: 0001_baseline's `outbox` table was missing `version`,
`delivered_to`, and `next_attempt_at` (had a scalar `delivered_at` instead), which the
shared relay's hard-coded SELECT requires -- the first real call would have failed with a
column-does-not-exist error. Fixed in migrations/versions/0002_outbox_align_schema.py.
"""

from __future__ import annotations

import json
import uuid

import pytest


@pytest.fixture(autouse=True)
def _flush_env(monkeypatch):
    monkeypatch.setenv("PS_PAYPALADAPTER_OUTBOX_FLUSH_SECRET", "test-flush-secret")
    # Port 1 is reserved/unassigned -- connection refused immediately, no real network
    # dependency or timeout flakiness.
    monkeypatch.setenv("PS_PAYPALADAPTER_OUTBOX_RELAY_AUDIT_BASE_URL", "http://127.0.0.1:1")


async def test_flush_requires_tick_secret(client):
    resp = await client.post("/internal/outbox/flush")
    assert resp.status_code == 401


async def test_flush_leaves_row_pending_when_audit_unreachable(client, pg_env):
    import asyncpg

    event_id = str(uuid.uuid4())
    conn = await asyncpg.connect(
        f"postgresql://postgres:postgres@localhost:5432/{pg_env['db_name']}"
    )
    try:
        await conn.execute(
            """
            INSERT INTO paypal.outbox (event_id, type, aggregate_id, payload, trace_id)
            VALUES ($1, 'paypal.call_recorded', $2, $3::jsonb, $4)
            """,
            event_id,
            "agg-1",
            json.dumps({"hello": "world"}),
            str(uuid.uuid4()),
        )
    finally:
        await conn.close()

    resp = await client.post(
        "/internal/outbox/flush",
        headers={"X-Tick-Secret": "test-flush-secret"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["delivered"] == 0
    assert body["failed"] >= 1
    assert body["pending"] >= 1

    conn = await asyncpg.connect(
        f"postgresql://postgres:postgres@localhost:5432/{pg_env['db_name']}"
    )
    try:
        row = await conn.fetchrow(
            "SELECT attempts, delivered_to, next_attempt_at FROM paypal.outbox WHERE event_id = $1",
            event_id,
        )
    finally:
        await conn.close()
    assert row is not None
    assert row["attempts"] == 1
    assert row["delivered_to"] == "{}"
    assert row["next_attempt_at"] is not None
