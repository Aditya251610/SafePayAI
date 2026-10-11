"""GET /grants - stubs per mandate/api.md section 11."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.deps import Principal, verify_internal_jwt

router = APIRouter(tags=["grants"])


@router.get("/grants")
async def list_grants(
    response: Response, order_id: str | None = None, principal: Principal = Depends(verify_internal_jwt)
) -> dict:
    response.status_code = 501
    return {"error": "not_implemented", "detail": "GET /grants pending Wave 5"}


@router.get("/grants/{grant_id}")
async def get_grant(
    grant_id: str, response: Response, principal: Principal = Depends(verify_internal_jwt)
) -> dict:
    response.status_code = 501
    return {"error": "not_implemented", "detail": "GET /grants/{grant_id} pending Wave 5"}
