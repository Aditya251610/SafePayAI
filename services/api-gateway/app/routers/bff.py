"""Read-only BFF aggregators - stubs per spec.md section 9 / api.md section 3.

P1, cut if api-gateway spec.md C9's missing list endpoints never land; kept here
as a stub so the contract exists.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.deps import Principal, require_buyer, require_staff

router = APIRouter(prefix="/api/bff", tags=["bff"])


def _not_implemented(response: Response, path: str) -> dict:
    response.status_code = 501
    return {"error": "not_implemented", "detail": f"{path} pending Wave 5"}


@router.get("/buyer-home")
async def buyer_home(response: Response, principal: Principal = Depends(require_buyer)) -> dict:
    return _not_implemented(response, "GET /api/bff/buyer-home")


@router.get("/orders/{order_id}")
async def order_detail(
    order_id: str, response: Response, principal: Principal = Depends(require_buyer)
) -> dict:
    return _not_implemented(response, "GET /api/bff/orders/{id}")


@router.get("/merchant-queue")
async def merchant_queue(response: Response, principal: Principal = Depends(require_staff)) -> dict:
    return _not_implemented(response, "GET /api/bff/merchant-queue")
