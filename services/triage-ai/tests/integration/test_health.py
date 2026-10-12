"""Real-DB smoke test: migrations apply cleanly (role bootstrap DO-block + schema-commit
fix, see migrations/env.py and versions/0001_baseline.py) and /readyz reaches Postgres over
the runtime role svc_triage (not the superuser)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


async def test_healthz_does_not_touch_db(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "triage-ai"}


async def test_readyz_reaches_db_over_runtime_role(client):
    resp = await client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["db"] == "ok"
