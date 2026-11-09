"""GET /api/wake: configured URLs only, rate limited, harmless when unset."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    from app.main import app
    from app.ratelimit import limiter

    limiter.reset()
    return TestClient(app, base_url="https://testserver"), monkeypatch


def test_unset_is_a_noop(client) -> None:
    c, mp = client
    mp.delenv("PS_APIGATEWAY_WAKE_URLS", raising=False)
    r = c.get("/api/wake")
    assert r.status_code == 200
    assert r.json() == {"pinged": 0}


def test_pings_only_configured_urls_and_survives_failures(client) -> None:
    c, mp = client
    mp.setenv("PS_APIGATEWAY_WAKE_URLS", "https://a.test/health, https://b.test/health")
    seen: list[str] = []

    async def _fake_get(self, url, *a, **k):
        seen.append(str(url))
        raise httpx.ConnectTimeout("asleep")

    mp.setattr(httpx.AsyncClient, "get", _fake_get)
    r = c.get("/api/wake", params={"url": "https://evil.test/"})
    assert r.status_code == 200
    assert r.json() == {"pinged": 2}
    assert sorted(seen) == ["https://a.test/health", "https://b.test/health"]


def test_rate_limited(client) -> None:
    c, mp = client
    mp.delenv("PS_APIGATEWAY_WAKE_URLS", raising=False)
    codes = [c.get("/api/wake").status_code for _ in range(14)]
    assert codes[:12] == [200] * 12
    assert 429 in codes[12:]
