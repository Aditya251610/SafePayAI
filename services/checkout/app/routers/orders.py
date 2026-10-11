"""Order lifecycle endpoints -- api.md sections 5-9. Wave 4: validated stubs, 501.

Return/capture/receipt business logic (checkout/spec.md sections 5-11) is Wave 5.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.deps import Principal, require_idempotency_key, require_service_jwt
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
    return _not_implemented("POST /orders/return pending Wave 5")


@router.post("/orders/cancel", status_code=501)
async def orders_cancel(
    body: OrderCancelRequest,
    _principal: Principal = Depends(require_service_jwt),
) -> JSONResponse:
    return _not_implemented("POST /orders/cancel pending Wave 5")


@router.post("/orders/{order_id}/capture", status_code=501)
async def capture_order(
    order_id: str,
    _principal: Principal = Depends(require_service_jwt),
    _idem: str = Depends(require_idempotency_key),
) -> JSONResponse:
    return _not_implemented("POST /orders/{order_id}/capture pending Wave 5")


@router.get("/orders/{order_id}", status_code=501)
async def get_order(
    order_id: str,
    _principal: Principal = Depends(require_service_jwt),
) -> JSONResponse:
    return _not_implemented("GET /orders/{order_id} pending Wave 5")


@router.get("/orders/{order_id}/receipt", status_code=501)
async def get_receipt(
    order_id: str,
    _principal: Principal = Depends(require_service_jwt),
) -> JSONResponse:
    return _not_implemented("GET /orders/{order_id}/receipt pending Wave 5")


@router.get("/orders", status_code=501)
async def list_orders(
    mandate_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    _principal: Principal = Depends(require_service_jwt),
) -> JSONResponse:
    return _not_implemented("GET /orders pending Wave 5")
