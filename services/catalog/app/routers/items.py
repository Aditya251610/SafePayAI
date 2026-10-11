"""GET /items, GET /items/{sku} - stubs per catalog/api.md.

Wave 4: return 501 not_implemented. Wave 5 implements the resolve algorithm from
catalog/spec.md section 5 against the v_items_public view.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.deps import Principal, verify_internal_jwt

router = APIRouter(tags=["items"])


@router.get("/items")
async def list_items(response: Response, principal: Principal = Depends(verify_internal_jwt)) -> dict:
    response.status_code = 501
    return {"error": "not_implemented", "detail": "GET /items pending Wave 5"}


@router.get("/items/{sku}")
async def get_item(sku: str, response: Response, principal: Principal = Depends(verify_internal_jwt)) -> dict:
    response.status_code = 501
    return {"error": "not_implemented", "detail": "GET /items/{sku} pending Wave 5"}
