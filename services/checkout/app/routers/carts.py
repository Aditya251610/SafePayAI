"""POST /carts, GET /carts/{cart_id}, POST /carts/{cart_id}/confirm -- api.md sections 3-4.

Wave 4: validated stubs, 501. Re-pricing / mandate-evaluate / intent-fit pipeline (spec.md
section 4) is Wave 5.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.deps import Principal, require_idempotency_key, require_service_jwt
from app.schemas.carts import ConfirmCartRequest, CreateCartRequest

router = APIRouter(tags=["carts"])


def _not_implemented(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={"error": "not_implemented", "detail": detail, "request_id": None},
    )


@router.post("/carts", status_code=501)
async def create_cart(
    body: CreateCartRequest,
    _principal: Principal = Depends(require_service_jwt),
) -> JSONResponse:
    return _not_implemented("POST /carts pending Wave 5")


@router.get("/carts/{cart_id}", status_code=501)
async def get_cart(
    cart_id: str,
    _principal: Principal = Depends(require_service_jwt),
) -> JSONResponse:
    return _not_implemented("GET /carts/{cart_id} pending Wave 5")


@router.post("/carts/{cart_id}/confirm", status_code=501)
async def confirm_cart(
    cart_id: str,
    body: ConfirmCartRequest,
    _principal: Principal = Depends(require_service_jwt),
    _idem: str = Depends(require_idempotency_key),
) -> JSONResponse:
    return _not_implemented("POST /carts/{cart_id}/confirm pending Wave 5")
