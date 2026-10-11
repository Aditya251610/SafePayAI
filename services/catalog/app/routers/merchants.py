"""GET /merchants, GET /merchants/{id}/refund-policy-seed - stubs per catalog/api.md."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.deps import Principal, verify_internal_jwt

router = APIRouter(tags=["merchants"])


@router.get("/merchants")
async def list_merchants(response: Response, principal: Principal = Depends(verify_internal_jwt)) -> dict:
    response.status_code = 501
    return {"error": "not_implemented", "detail": "GET /merchants pending Wave 5"}


@router.get("/merchants/{merchant_id}/refund-policy-seed")
async def refund_policy_seed(
    merchant_id: str, response: Response, principal: Principal = Depends(verify_internal_jwt)
) -> dict:
    response.status_code = 501
    return {
        "error": "not_implemented",
        "detail": "GET /merchants/{id}/refund-policy-seed pending Wave 5",
    }
