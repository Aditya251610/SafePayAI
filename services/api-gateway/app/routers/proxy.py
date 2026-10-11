"""Proxied endpoints: /api/<svc> + upstream path, per spec.md section 5.2 / api.md section 4.

Real forwarding via app.routing.proxy.forward: header allowlist, internal JWT mint,
forward, response filter, idempotency enforcement, money-routes brake. Request
bodies here stay untyped dicts since the real schemas live in each owning
service's OpenAPI contract, not this gateway's (spec.md section 2: "no business
logic").
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response

from app.deps import (
    Principal,
    require_buyer,
    require_merchant,
    require_operator,
    require_session,
    require_staff,
)
from app.routing.proxy import forward
from app.settings import Settings, get_settings

router = APIRouter(prefix="/api", tags=["proxy"])


def _demo_mode_gate(settings: Settings) -> None:
    if not settings.demo_mode:
        raise HTTPException(status_code=404, detail="NOT_FOUND")


# ---- mandate -----------------------------------------------------------------


@router.post("/mandate/mandates")
async def proxy_mandate_sign(
    request: Request,
    response: Response,
    body: dict[str, Any] = Body(default={}),
    principal: Principal = Depends(require_buyer),
) -> Any:
    return await forward(
        request,
        response,
        service="mandate",
        upstream_path="/mandates",
        method="POST",
        principal=principal,
        scope=["mandate:sign"],
        body=body,
        require_idempotency=True,
    )


@router.get("/mandate/mandates/{mandate_id}")
async def proxy_mandate_get(
    mandate_id: str,
    request: Request,
    response: Response,
    principal: Principal = Depends(require_session),
) -> Any:
    return await forward(
        request,
        response,
        service="mandate",
        upstream_path=f"/mandates/{mandate_id}",
        method="GET",
        principal=principal,
        scope=["mandate:read"],
        mandate_id=mandate_id,
    )


@router.get("/mandate/mandates/{mandate_id}/terms")
async def proxy_mandate_terms(
    mandate_id: str,
    request: Request,
    response: Response,
    principal: Principal = Depends(require_session),
) -> Any:
    return await forward(
        request,
        response,
        service="mandate",
        upstream_path=f"/mandates/{mandate_id}/terms",
        method="GET",
        principal=principal,
        scope=["mandate:read"],
        mandate_id=mandate_id,
    )


@router.post("/mandate/mandates/{mandate_id}/revoke")
async def proxy_mandate_revoke(
    mandate_id: str,
    request: Request,
    response: Response,
    principal: Principal = Depends(require_buyer),
) -> Any:
    return await forward(
        request,
        response,
        service="mandate",
        upstream_path=f"/mandates/{mandate_id}/revoke",
        method="POST",
        principal=principal,
        scope=["mandate:revoke"],
        mandate_id=mandate_id,
    )


# ---- catalog -------------------------------------------------------------------


@router.get("/catalog/items")
async def proxy_catalog_items(
    request: Request,
    response: Response,
    principal: Principal = Depends(require_session),
) -> Any:
    return await forward(
        request,
        response,
        service="catalog",
        upstream_path="/items",
        method="GET",
        principal=principal,
        scope=["catalog:read"],
    )


@router.get("/catalog/items/{sku}")
async def proxy_catalog_item(
    sku: str,
    request: Request,
    response: Response,
    principal: Principal = Depends(require_session),
) -> Any:
    return await forward(
        request,
        response,
        service="catalog",
        upstream_path=f"/items/{sku}",
        method="GET",
        principal=principal,
        scope=["catalog:read"],
    )


# ---- shopping-agent --------------------------------------------------------------


@router.post("/agent/propose")
async def proxy_agent_propose(
    request: Request,
    response: Response,
    body: dict[str, Any] = Body(default={}),
    principal: Principal = Depends(require_buyer),
) -> Any:
    return await forward(
        request,
        response,
        service="agent",
        upstream_path="/propose",
        method="POST",
        principal=principal,
        scope=["agent:propose"],
        body=body,
        require_idempotency=True,
    )


# ---- checkout ------------------------------------------------------------------


@router.post("/checkout/carts")
async def proxy_checkout_create_cart(
    request: Request,
    response: Response,
    body: dict[str, Any] = Body(default={}),
    principal: Principal = Depends(require_buyer),
) -> Any:
    return await forward(
        request,
        response,
        service="checkout",
        upstream_path="/carts",
        method="POST",
        principal=principal,
        scope=["checkout:cart"],
        body=body,
        require_idempotency=True,
    )


@router.post("/checkout/carts/{cart_id}/confirm")
async def proxy_checkout_confirm_cart(
    cart_id: str,
    request: Request,
    response: Response,
    body: dict[str, Any] = Body(default={}),
    principal: Principal = Depends(require_buyer),
) -> Any:
    return await forward(
        request,
        response,
        service="checkout",
        upstream_path=f"/carts/{cart_id}/confirm",
        method="POST",
        principal=principal,
        scope=["checkout:confirm"],
        body=body,
        require_idempotency=True,
        money_route=True,
    )


@router.post("/checkout/orders/{order_id}/capture")
async def proxy_checkout_capture(
    order_id: str,
    request: Request,
    response: Response,
    body: dict[str, Any] = Body(default={}),
    principal: Principal = Depends(require_buyer),
) -> Any:
    return await forward(
        request,
        response,
        service="checkout",
        upstream_path=f"/orders/{order_id}/capture",
        method="POST",
        principal=principal,
        scope=["checkout:capture"],
        body=body,
        require_idempotency=True,
        money_route=True,
    )


@router.get("/checkout/orders/{order_id}")
async def proxy_checkout_get_order(
    order_id: str,
    request: Request,
    response: Response,
    principal: Principal = Depends(require_session),
) -> Any:
    return await forward(
        request,
        response,
        service="checkout",
        upstream_path=f"/orders/{order_id}",
        method="GET",
        principal=principal,
        scope=["checkout:read"],
    )


@router.get("/checkout/orders")
async def proxy_checkout_list_orders(
    request: Request,
    response: Response,
    mandate_id: str | None = None,
    principal: Principal = Depends(require_session),
) -> Any:
    return await forward(
        request,
        response,
        service="checkout",
        upstream_path="/orders",
        method="GET",
        principal=principal,
        scope=["checkout:read"],
        mandate_id=mandate_id,
    )


# ---- tracking ------------------------------------------------------------------


@router.post("/tracking/shipments")
async def proxy_tracking_create_shipment(
    request: Request,
    response: Response,
    body: dict[str, Any] = Body(default={}),
    principal: Principal = Depends(require_merchant),
) -> Any:
    return await forward(
        request,
        response,
        service="tracking",
        upstream_path="/shipments",
        method="POST",
        principal=principal,
        scope=["tracking:write"],
        body=body,
        require_idempotency=True,
    )


@router.get("/tracking/shipments/{order_id}")
async def proxy_tracking_get_shipment(
    order_id: str,
    request: Request,
    response: Response,
    principal: Principal = Depends(require_session),
) -> Any:
    return await forward(
        request,
        response,
        service="tracking",
        upstream_path=f"/shipments/{order_id}",
        method="GET",
        principal=principal,
        scope=["tracking:read"],
    )


@router.post("/tracking/demo/clock/advance")
async def proxy_tracking_demo_clock_advance(
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
    principal: Principal = Depends(require_operator),
) -> Any:
    _demo_mode_gate(settings)
    return await forward(
        request,
        response,
        service="tracking",
        upstream_path="/demo/clock/advance",
        method="POST",
        principal=principal,
        scope=["tracking:demo"],
    )


@router.post("/tracking/demo/shipments/{shipment_id}/force")
async def proxy_tracking_demo_force(
    shipment_id: str,
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
    principal: Principal = Depends(require_operator),
) -> Any:
    _demo_mode_gate(settings)
    return await forward(
        request,
        response,
        service="tracking",
        upstream_path=f"/demo/shipments/{shipment_id}/force",
        method="POST",
        principal=principal,
        scope=["tracking:demo"],
    )


# ---- resolution ----------------------------------------------------------------


@router.post("/resolution/cases/report")
async def proxy_resolution_report(
    request: Request,
    response: Response,
    body: dict[str, Any] = Body(default={}),
    principal: Principal = Depends(require_buyer),
) -> Any:
    return await forward(
        request,
        response,
        service="resolution",
        upstream_path="/cases/report",
        method="POST",
        principal=principal,
        scope=["resolution:report"],
        body=body,
        require_idempotency=True,
    )


@router.get("/resolution/cases/{case_id}")
async def proxy_resolution_get_case(
    case_id: str,
    request: Request,
    response: Response,
    principal: Principal = Depends(require_session),
) -> Any:
    return await forward(
        request,
        response,
        service="resolution",
        upstream_path=f"/cases/{case_id}",
        method="GET",
        principal=principal,
        scope=["resolution:read"],
    )


@router.get("/resolution/cases")
async def proxy_resolution_list_cases(
    request: Request,
    response: Response,
    status: str | None = None,
    principal: Principal = Depends(require_staff),
) -> Any:
    return await forward(
        request,
        response,
        service="resolution",
        upstream_path="/cases",
        method="GET",
        principal=principal,
        scope=["resolution:list"],
    )


@router.post("/resolution/offers/{offer_id}/accept")
async def proxy_resolution_offer_accept(
    offer_id: str,
    request: Request,
    response: Response,
    principal: Principal = Depends(require_buyer),
) -> Any:
    return await forward(
        request,
        response,
        service="resolution",
        upstream_path=f"/offers/{offer_id}/accept",
        method="POST",
        principal=principal,
        scope=["resolution:accept"],
        require_idempotency=True,
        money_route=True,
    )


@router.post("/resolution/approvals/{token}/consent")
async def proxy_resolution_approval_consent(
    token: str,
    request: Request,
    response: Response,
    principal: Principal = Depends(require_buyer),
) -> Any:
    return await forward(
        request,
        response,
        service="resolution",
        upstream_path=f"/approvals/{token}/consent",
        method="POST",
        principal=principal,
        scope=["resolution:consent"],
        require_idempotency=True,
        money_route=True,
    )


@router.post("/resolution/cases/{case_id}/merchant-action")
async def proxy_resolution_merchant_action(
    case_id: str,
    request: Request,
    response: Response,
    body: dict[str, Any] = Body(default={}),
    principal: Principal = Depends(require_merchant),
) -> Any:
    return await forward(
        request,
        response,
        service="resolution",
        upstream_path=f"/cases/{case_id}/merchant-action",
        method="POST",
        principal=principal,
        scope=["resolution:merchant_action"],
        body=body,
        require_idempotency=True,
    )


# ---- audit (read-only) -----------------------------------------------------------


@router.get("/audit/entries")
async def proxy_audit_entries(
    request: Request,
    response: Response,
    principal: Principal = Depends(require_session),
) -> Any:
    return await forward(
        request,
        response,
        service="audit",
        upstream_path="/entries",
        method="GET",
        principal=principal,
        scope=["audit:read"],
    )


@router.get("/audit/verify")
async def proxy_audit_verify(
    request: Request,
    response: Response,
    principal: Principal = Depends(require_session),
) -> Any:
    return await forward(
        request,
        response,
        service="audit",
        upstream_path="/verify",
        method="GET",
        principal=principal,
        scope=["audit:read"],
    )
