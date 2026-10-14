"""Read-only BFF aggregators - spec.md section 9 / api.md section 3.

`buyer-home` is deliberately left unimplemented: spec.md C9 flags it as needing
"mandate list by buyer" and "checkout orders by buyer" list endpoints that don't
exist anywhere in the service-map (mandate has no GET /mandates list; checkout's
GET /orders requires an explicit mandate_id, it can't enumerate a buyer's
mandates to know which ones to ask for) -- the spec's own documented contingency
is "if not added, buyer-home is cut, UI uses direct proxied reads" (api.md
section 9). Building a new list-by-buyer endpoint on mandate or checkout is a
separate, bigger piece of work, not a gateway-only aggregation job.

`orders/{id}` and `merchant-queue` have no such missing dependency -- every piece
they aggregate already exists -- so those are implemented for real below.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Response

from app.deps import Principal, require_buyer, require_staff
from app.settings import get_settings
from app.tokens.mint import mint_for_upstream
from app.upstream import UpstreamNotConfigured, get_upstream_client

router = APIRouter(prefix="/api/bff", tags=["bff"])


def _not_implemented(response: Response, path: str) -> dict:
    response.status_code = 501
    return {"error": "not_implemented", "detail": f"{path} pending Wave 5"}


async def _get(
    service: str,
    path: str,
    *,
    principal: Principal,
    scope: list[str],
    params: dict[str, Any] | None = None,
) -> Any | None:
    """One best-effort aggregator leg: returns the parsed JSON body on a 2xx, or
    None on anything else (not found, upstream down, wrong role) -- a BFF read is
    allowed to show partial data, unlike a single proxied call that must surface
    the real error."""
    settings = get_settings()
    try:
        client = get_upstream_client(service, settings)
    except UpstreamNotConfigured:
        return None
    token = mint_for_upstream(
        principal, audience=service, request_id=str(uuid.uuid4()), scope=scope
    )
    try:
        resp = await client.get(
            path, params=params or {}, headers={"Authorization": f"Bearer {token}"}
        )
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout):
        return None
    if resp.status_code != 200:
        return None
    try:
        return resp.json()
    except ValueError:
        return None


@router.get("/buyer-home")
async def buyer_home(
    response: Response, principal: Principal = Depends(require_buyer)
) -> dict:
    return _not_implemented(response, "GET /api/bff/buyer-home")


@router.get("/orders/{order_id}")
async def order_detail(
    order_id: str, response: Response, principal: Principal = Depends(require_buyer)
) -> dict:
    order = await _get(
        "checkout",
        f"/orders/{order_id}",
        principal=principal,
        scope=["checkout:read"],
    )
    if order is None:
        response.status_code = 404
        return {"error": "ORDER_NOT_FOUND", "message": "order not found"}

    shipment = await _get(
        "tracking",
        f"/shipments/{order_id}",
        principal=principal,
        scope=["tracking:read"],
    )
    case = await _get(
        "resolution",
        "/cases",
        principal=principal,
        scope=["resolution:read"],
        params={"order_id": order_id},
    )
    audit = await _get("audit", "/verify", principal=principal, scope=["audit:read"])

    cases = (case or {}).get("items") or []
    response.status_code = 200
    return {
        "order": order,
        "shipment": shipment,
        "case": cases[0] if cases else None,
        "audit_verified": (audit or {}).get("ok") if audit is not None else None,
    }


@router.get("/merchant-queue")
async def merchant_queue(
    response: Response, principal: Principal = Depends(require_staff)
) -> dict:
    cases = await _get(
        "resolution",
        "/cases",
        principal=principal,
        scope=["resolution:read"],
        params={"status": "HUMAN_REVIEW"},
    )
    response.status_code = 200
    return {
        "cases": (cases or {}).get("items") or [],
        # tracking has no "list shipments pending" endpoint (only per-order lookup)
        # to aggregate a platform-wide pending count from -- flagged, not faked.
        "tracking_pending": None,
    }
