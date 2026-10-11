"""Order lifecycle endpoints -- api.md sections 5-9.

Wave 5B scope (sprint-plan S1-09): GET /orders/{order_id} and GET /orders are real.
POST /orders/return, /orders/cancel, /orders/{id}/capture remain 501 -- deferred,
NOT an oversight: paypal-adapter's own create_order/get_order/capture_order endpoints
are themselves still Wave-4 stubs in this repo (services/paypal-adapter/app/routers/
orders.py), and the return flow needs a live `GET /v1/orders/{id}` to verify APPROVED
status plus the ticket HMAC wiring (PS_CHECKOUT_TICKET_HMAC_KEY, not yet provisioned).
Implementing a capture path against a stub adapter would not exercise anything real;
wiring it up is tracked for the wave that lands paypal-adapter's S1-08 scope.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import repo
from app.db import get_db
from app.deps import Principal, require_idempotency_key, require_service_jwt
from app.errors import CheckoutError
from app.schemas.carts import OrderCancelRequest, OrderReturnRequest

router = APIRouter(tags=["orders"])


def _not_implemented(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={"error": "not_implemented", "detail": detail, "request_id": None},
    )


@router.post("/orders/return", status_code=501)
async def orders_return(
    body: OrderReturnRequest,
    _principal: Principal = Depends(require_service_jwt),
) -> JSONResponse:
    return _not_implemented("POST /orders/return pending paypal-adapter S1-08")


@router.post("/orders/cancel", status_code=501)
async def orders_cancel(
    body: OrderCancelRequest,
    _principal: Principal = Depends(require_service_jwt),
) -> JSONResponse:
    return _not_implemented("POST /orders/cancel pending paypal-adapter S1-08")


@router.post("/orders/{order_id}/capture", status_code=501)
async def capture_order(
    order_id: str,
    _principal: Principal = Depends(require_service_jwt),
    _idem: str = Depends(require_idempotency_key),
) -> JSONResponse:
    return _not_implemented(
        "POST /orders/{order_id}/capture pending paypal-adapter S1-08"
    )


def _buyer_id(principal: Principal) -> str:
    return principal.buyer_id or principal.sub


def _order_view(row: dict) -> dict:
    return {
        "order_id": str(row["order_id"]),
        "cart_id": str(row["cart_id"]),
        "mandate_id": str(row["mandate_id"]),
        "status": row["status"],
        "total_minor": row["total_minor"],
        "currency": row["currency"],
        "paypal_order_id": row["paypal_order_id"],
        "approve_url": row["approve_url"],
        "failure_code": row["failure_code"],
        "created_at": row["created_at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
        "updated_at": row["updated_at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@router.get("/orders/{order_id}")
async def get_order(
    order_id: str,
    principal: Principal = Depends(require_service_jwt),
    session: AsyncSession = Depends(get_db),
) -> dict:
    async with session.begin():
        row = await repo.get_order_row(session, order_id)
    if row is None:
        raise CheckoutError(404, "ORDER_NOT_FOUND", "order not found")
    if principal.role == "buyer" and str(row["buyer_id"]) != _buyer_id(principal):
        raise CheckoutError(404, "ORDER_NOT_FOUND", "order not found")
    return _order_view(row)


@router.get("/orders/{order_id}/receipt", status_code=501)
async def get_receipt(
    order_id: str,
    _principal: Principal = Depends(require_service_jwt),
) -> JSONResponse:
    return _not_implemented(
        "GET /orders/{order_id}/receipt pending capture path (S1-08)"
    )


@router.get("/orders")
async def list_orders(
    mandate_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    principal: Principal = Depends(require_service_jwt),
    session: AsyncSession = Depends(get_db),
) -> dict:
    if mandate_id is None:
        raise CheckoutError(
            422, "VALIDATION_ERROR", "mandate_id query param is required"
        )
    async with session.begin():
        from sqlalchemy import text

        query = "SELECT * FROM checkout.orders WHERE mandate_id = :mandate_id"
        params: dict[str, object] = {"mandate_id": mandate_id}
        if status is not None:
            query += " AND status = :status"
            params["status"] = status
        result = await session.execute(text(query), params)
        rows = [dict(r) for r in result.mappings().all()]
    buyer_id = _buyer_id(principal)
    if principal.role == "buyer":
        rows = [r for r in rows if str(r["buyer_id"]) == buyer_id]
    return {"items": [_order_view(r) for r in rows]}
