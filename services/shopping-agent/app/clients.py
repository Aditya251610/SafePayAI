"""Thin HTTP clients for the two peers this service reads from (spec.md section 1):
`catalog` (`GET /items`) and `mandate` (`GET /mandates/{id}/summary`).

`bearer_token` is minted fresh per call by the caller via `app.deps.mint_outbound_token`
(audience="catalog"/"mandate") - found live that this used to forward whatever inbound
token the caller already had (aud="agent", this service's own audience), which every
downstream service's audience check correctly rejected. Both calls fail closed to the
documented 503 codes (`CATALOG_UNAVAILABLE` / `MANDATE_UNAVAILABLE`) on any transport
error, timeout, or non-2xx response -- never a silent empty result.
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


_CATALOG_PAGE_LIMIT = 100  # catalog/app/routers/items.py's own MAX_LIMIT
_CATALOG_FETCH_CEILING = 1000  # hard stop so a runaway catalog can't stall a request


def _to_agent_item(raw: dict[str, Any]) -> dict[str, Any]:
    """Maps catalog's real `Item` shape (category_id, unit_price_minor) to the field
    names the agent's own internals (prompts.py, catalog_filter.py, form_fallback.py)
    have always used (category, price_minor) -- one mapping at the boundary instead of
    rewriting every internal call site, and the only place this divergence can hide
    again."""
    mapped = dict(raw)
    if "category_id" in mapped:
        mapped["category"] = mapped.pop("category_id")
    if "unit_price_minor" in mapped:
        mapped["price_minor"] = mapped.pop("unit_price_minor")
    return mapped


async def fetch_catalog_items(
    *, base_url: str, bearer_token: str | None, timeout_s: float = 5.0
) -> list[dict[str, Any]]:
    headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}
    items: list[dict[str, Any]] = []
    offset = 0
    try:
        async with build_client(base_url) as client:
            while True:
                response = await client.get(
                    "/items",
                    params={"limit": _CATALOG_PAGE_LIMIT, "offset": offset},
                    headers=headers,
                    timeout=timeout_s,
                )
                response.raise_for_status()
                body = response.json()
                page = body.get("items")
                if not isinstance(page, list):
                    raise CatalogUnavailableError(
                        "catalog /items returned no items array"
                    )
                items.extend(page)
                if not body.get("has_more") or len(items) >= _CATALOG_FETCH_CEILING:
                    break
                offset += _CATALOG_PAGE_LIMIT
    except (httpx.HTTPError, ValueError) as exc:
        raise CatalogUnavailableError(
            f"catalog /items unreachable or invalid: {exc}"
        ) from exc
    return [_to_agent_item(item) for item in items if item.get("active", True)]


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
