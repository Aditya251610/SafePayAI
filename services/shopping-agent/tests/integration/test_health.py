"""Real-DB smoke test: migrations apply cleanly and /readyz reaches Postgres over the
runtime role (not the superuser), exercising the grants from 0001_baseline.py.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


async def test_healthz_does_not_touch_db(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_readyz_reaches_db_over_runtime_role(client):
    resp = await client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["db"] == "ok"
