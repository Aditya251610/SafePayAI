from __future__ import annotations

import httpx
import pytest

from app_checkout.routers import health


@pytest.mark.asyncio
async def test_adapter_probe_uses_health_path(monkeypatch) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200 if request.url.path == "/health" else 404)

    real = httpx.AsyncClient

    def fake_build_client(base_url, timeout=None, **kw):
        return real(base_url=base_url, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(health, "build_client", fake_build_client)
    assert await health._check_upstream("http://a", health.ADAPTER_HEALTH_PATH) is True
    assert await health._check_upstream("http://a") is False  # default /healthz -> 404
    assert seen == ["/health", "/healthz"]
