"""Upstream httpx client management (spec.md section 2 `upstream.py`, section 5.2).

Uses `libs/common.http.client.build_client` (the shared httpx wrapper with
timeout/retry defaults) rather than constructing `httpx.AsyncClient` from scratch -
per the task brief, this is the "libs/common HTTP client wrapper" every service is
asked to reuse. One client per upstream service slug, cached for the process
lifetime. `PS_APIGATEWAY_UPSTREAM_MODE=inprocess` (ASGITransport, Profile B
co-located) is not wired in this pass - only `http` mode is implemented; flagged in
the final report as a scope cut (not in this task's numbered IMPLEMENT list, and no
co-located ASGI app exists yet for any upstream to mount).
"""

from __future__ import annotations

import httpx
from safepayai_common.http.client import build_client

from app.settings import Settings, get_settings

# Maps the public `/api/<svc>/...` slug to the Settings attribute holding its base URL.
UPSTREAM_SETTINGS_ATTR = {
    "mandate": "upstream_mandate_url",
    "catalog": "upstream_catalog_url",
    "agent": "upstream_shopping_agent_url",
    "checkout": "upstream_checkout_url",
    "tracking": "upstream_tracking_url",
    "resolution": "upstream_resolution_url",
    "audit": "upstream_audit_url",
}

_clients: dict[str, httpx.AsyncClient] = {}


class UpstreamNotConfigured(RuntimeError):
    pass


def get_upstream_client(
    service: str, settings: Settings | None = None
) -> httpx.AsyncClient:
    settings = settings or get_settings()
    if service not in UPSTREAM_SETTINGS_ATTR:
        raise UpstreamNotConfigured(f"unknown upstream service {service!r}")

    base_url = getattr(settings, UPSTREAM_SETTINGS_ATTR[service])
    if not base_url:
        raise UpstreamNotConfigured(f"no upstream URL configured for {service!r}")

    client = _clients.get(service)
    if client is None or str(client.base_url).rstrip("/") != base_url.rstrip("/"):
        timeout = httpx.Timeout(
            connect=settings.upstream_connect_timeout_s,
            read=settings.upstream_read_timeout_s,
            write=settings.upstream_read_timeout_s,
            pool=settings.upstream_read_timeout_s,
        )
        client = build_client(base_url, timeout=timeout)
        _clients[service] = client
    return client


def set_upstream_client(service: str, client: httpx.AsyncClient) -> None:
    """Test/inprocess seam: inject a client bound to an ASGITransport pointed at a
    fake upstream app, bypassing real network I/O."""
    _clients[service] = client


def reset_upstream_clients() -> None:
    _clients.clear()
