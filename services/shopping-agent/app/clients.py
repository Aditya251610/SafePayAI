"""Thin HTTP clients for the two peers this service reads from (spec.md section 1):
`catalog` (`GET /items`) and `mandate` (`GET /mandates/{id}/summary`).

Known gap, documented rather than silently guessed at: full service-to-service auth
(minting this service's own signed internal JWT via safepayai_common.auth.jwt) is not
yet wired anywhere in this service's settings (no signing-key config exists here), and
is out of scope for this task's build spec (LLM wiring, not the auth-gateway/service-
identity rollout). This module forwards whatever bearer token the caller already has
(the buyer's or checkout's own internal JWT) as a best-effort interim; properly minting
a `shopping-agent -> catalog`/`shopping-agent -> mandate` service token is tracked as
follow-up work, not invented here. Both calls fail closed to the documented 503 codes
(`CATALOG_UNAVAILABLE` / `MANDATE_UNAVAILABLE`) on any transport error, timeout, or
non-2xx response -- never a silent empty result.
"""

from __future__ import annotations

from typing import Any

import httpx
from safepayai_common.http.client import build_client


class CatalogUnavailableError(Exception):
    """Raised on any failure reading the catalog (connection error, timeout, non-2xx)."""


class MandateUnavailableError(Exception):
    """Raised on any failure reading the mandate summary, EXCEPT not-found (see below)."""


class MandateNotFoundError(Exception):
    """Raised when the mandate does not exist or is not owned by the caller (404)."""


async def fetch_catalog_items(
    *, base_url: str, bearer_token: str | None, timeout_s: float = 5.0
) -> list[dict[str, Any]]:
    headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}
    try:
        async with build_client(base_url) as client:
            response = await client.get("/items", headers=headers, timeout=timeout_s)
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise CatalogUnavailableError(
            f"catalog /items unreachable or invalid: {exc}"
        ) from exc
    items = body.get("items")
    if not isinstance(items, list):
        raise CatalogUnavailableError("catalog /items returned no items array")
    return items


async def fetch_mandate_summary(
    *, base_url: str, mandate_id: str, bearer_token: str | None, timeout_s: float = 5.0
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}
    try:
        async with build_client(base_url) as client:
            response = await client.get(
                f"/mandates/{mandate_id}/summary", headers=headers, timeout=timeout_s
            )
    except httpx.HTTPError as exc:
        raise MandateUnavailableError(f"mandate /summary unreachable: {exc}") from exc

    if response.status_code == 404:
        raise MandateNotFoundError(f"mandate {mandate_id} not found")
    try:
        response.raise_for_status()
        body: dict[str, Any] = response.json()
        return body
    except (httpx.HTTPError, ValueError) as exc:
        raise MandateUnavailableError(
            f"mandate /summary invalid response: {exc}"
        ) from exc


__all__ = [
    "CatalogUnavailableError",
    "MandateNotFoundError",
    "MandateUnavailableError",
    "fetch_catalog_items",
    "fetch_mandate_summary",
]
