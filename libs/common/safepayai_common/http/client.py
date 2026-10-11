"""Shared httpx client defaults: timeouts, retry-on-connect-error, no business logic."""

from __future__ import annotations

import httpx

DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)


def build_client(base_url: str, timeout: httpx.Timeout = DEFAULT_TIMEOUT) -> httpx.AsyncClient:
    transport = httpx.AsyncHTTPTransport(retries=2)
    return httpx.AsyncClient(base_url=base_url, timeout=timeout, transport=transport)
