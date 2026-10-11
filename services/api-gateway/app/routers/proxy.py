"""Proxied endpoints: /api/<svc> + upstream path, per spec.md section 5.2 / api.md section 4.

Wave 4: every proxied route is a stub returning 501 (conventions doc section 1).
The actual proxy mechanics (header allowlist, token mint, forward, response
filter, idempotency, retries) are Wave 5's routing/proxy.py. Request bodies here
are untyped dicts since the real schemas live in each owning service's OpenAPI
contract, not this gateway's (spec.md section 2: "no business logic").
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Response

from app.deps import Principal, require_buyer, require_merchant, require_session, require_staff

router = APIRouter(prefix="/api", tags=["proxy"])


def _not_implemented(response: Response, path: str) -> dict:
    response.status_code = 501
    return {"error": "not_implemented", "detail": f"{path} pending Wave 5"}


# ---- mandate -----------------------------------------------------------------


@router.post("/mandate/mandates")
async def proxy_mandate_sign(
    response: Response, body: dict[str, Any] = Body(default={}), principal: Principal = Depends(require_buyer)
) -> dict:
    return _not_implemented(response, "POST /api/mandate/mandates")


@router.get("/mandate/mandates/{mandate_id}")
async def proxy_mandate_get(
    mandate_id: str, response: Response, principal: Principal = Depends(require_session)
) -> dict:
    return _not_implemented(response, "GET /api/mandate/mandates/{id}")


@router.get("/mandate/mandates/{mandate_id}/terms")
async def proxy_mandate_terms(
    mandate_id: str, response: Response, principal: Principal = Depends(require_session)
) -> dict:
    return _not_implemented(response, "GET /api/mandate/mandates/{id}/terms")


@router.post("/mandate/mandates/{mandate_id}/revoke")
async def proxy_mandate_revoke(
    mandate_id: str, response: Response, principal: Principal = Depends(require_buyer)
) -> dict:
    return _not_implemented(response, "POST /api/mandate/mandates/{id}/revoke")


# ---- catalog -------------------------------------------------------------------


@router.get("/catalog/items")
async def proxy_catalog_items(response: Response, principal: Principal = Depends(require_session)) -> dict:
    return _not_implemented(response, "GET /api/catalog/items")


@router.get("/catalog/items/{sku}")
async def proxy_catalog_item(
    sku: str, response: Response, principal: Principal = Depends(require_session)
) -> dict:
    return _not_implemented(response, "GET /api/catalog/items/{id}")


# ---- shopping-agent --------------------------------------------------------------


@router.post("/agent/propose")
async def proxy_agent_propose(
    response: Response, body: dict[str, Any] = Body(default={}), principal: Principal = Depends(require_buyer)
) -> dict:
    return _not_implemented(response, "POST /api/agent/propose")


# ---- checkout ------------------------------------------------------------------


@router.post("/checkout/carts")
async def proxy_checkout_create_cart(
    response: Response, body: dict[str, Any] = Body(default={}), principal: Principal = Depends(require_buyer)
) -> dict:
    return _not_implemented(response, "POST /api/checkout/carts")


@router.post("/checkout/carts/{cart_id}/confirm")
async def proxy_checkout_confirm_cart(
    cart_id: str, response: Response, principal: Principal = Depends(require_buyer)
) -> dict:
    return _not_implemented(response, "POST /api/checkout/carts/{id}/confirm")


@router.post("/checkout/orders/{order_id}/capture")
async def proxy_checkout_capture(
    order_id: str,
    response: Response,
    body: dict[str, Any] = Body(default={}),
    principal: Principal = Depends(require_buyer),
) -> dict:
    return _not_implemented(response, "POST /api/checkout/orders/{id}/capture")


@router.get("/checkout/orders/{order_id}")
async def proxy_checkout_get_order(
    order_id: str, response: Response, principal: Principal = Depends(require_session)
) -> dict:
    return _not_implemented(response, "GET /api/checkout/orders/{id}")


@router.get("/checkout/orders")
async def proxy_checkout_list_orders(
    response: Response, mandate_id: str | None = None, principal: Principal = Depends(require_session)
) -> dict:
    return _not_implemented(response, "GET /api/checkout/orders")


# ---- tracking ------------------------------------------------------------------


@router.post("/tracking/shipments")
async def proxy_tracking_create_shipment(
    response: Response, body: dict[str, Any] = Body(default={}), principal: Principal = Depends(require_merchant)
) -> dict:
    return _not_implemented(response, "POST /api/tracking/shipments")


@router.get("/tracking/shipments/{order_id}")
async def proxy_tracking_get_shipment(
    order_id: str, response: Response, principal: Principal = Depends(require_session)
) -> dict:
    return _not_implemented(response, "GET /api/tracking/shipments/{order_id}")


@router.post("/tracking/demo/clock/advance")
async def proxy_tracking_demo_clock_advance(
    response: Response, principal: Principal = Depends(require_session)
) -> dict:
    # NOTE: role should be operator-only and gated by PS_APIGATEWAY_DEMO_MODE
    # (else 404) per spec.md section 5.2; enforced in Wave 5.
    return _not_implemented(response, "POST /api/tracking/demo/clock/advance")


@router.post("/tracking/demo/shipments/{shipment_id}/force")
async def proxy_tracking_demo_force(
    shipment_id: str, response: Response, principal: Principal = Depends(require_session)
) -> dict:
    return _not_implemented(response, "POST /api/tracking/demo/shipments/{id}/force")


# ---- resolution ----------------------------------------------------------------


@router.post("/resolution/cases/report")
async def proxy_resolution_report(
    response: Response, body: dict[str, Any] = Body(default={}), principal: Principal = Depends(require_buyer)
) -> dict:
    return _not_implemented(response, "POST /api/resolution/cases/report")


@router.get("/resolution/cases/{case_id}")
async def proxy_resolution_get_case(
    case_id: str, response: Response, principal: Principal = Depends(require_session)
) -> dict:
    return _not_implemented(response, "GET /api/resolution/cases/{id}")


@router.get("/resolution/cases")
async def proxy_resolution_list_cases(
    response: Response, status: str | None = None, principal: Principal = Depends(require_staff)
) -> dict:
    return _not_implemented(response, "GET /api/resolution/cases")


@router.post("/resolution/offers/{offer_id}/accept")
async def proxy_resolution_offer_accept(
    offer_id: str, response: Response, principal: Principal = Depends(require_buyer)
) -> dict:
    return _not_implemented(response, "POST /api/resolution/offers/{id}/accept")


@router.post("/resolution/approvals/{token}/consent")
async def proxy_resolution_approval_consent(
    token: str, response: Response, principal: Principal = Depends(require_buyer)
) -> dict:
    return _not_implemented(response, "POST /api/resolution/approvals/{token}/consent")


@router.post("/resolution/cases/{case_id}/merchant-action")
async def proxy_resolution_merchant_action(
    case_id: str,
    response: Response,
    body: dict[str, Any] = Body(default={}),
    principal: Principal = Depends(require_merchant),
) -> dict:
    return _not_implemented(response, "POST /api/resolution/cases/{id}/merchant-action")


# ---- audit (read-only) -----------------------------------------------------------


@router.get("/audit/entries")
async def proxy_audit_entries(response: Response, principal: Principal = Depends(require_session)) -> dict:
    return _not_implemented(response, "GET /api/audit/entries")


@router.get("/audit/verify")
async def proxy_audit_verify(response: Response, principal: Principal = Depends(require_session)) -> dict:
    return _not_implemented(response, "GET /api/audit/verify")
