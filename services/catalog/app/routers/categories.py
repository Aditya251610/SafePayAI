"""GET /categories, GET /catalog/version - stubs per catalog/api.md."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.deps import Principal, verify_internal_jwt

router = APIRouter(tags=["categories"])


@router.get("/categories")
async def list_categories(response: Response, principal: Principal = Depends(verify_internal_jwt)) -> dict:
    response.status_code = 501
    return {"error": "not_implemented", "detail": "GET /categories pending Wave 5"}


@router.get("/catalog/version")
async def catalog_version(response: Response, principal: Principal = Depends(verify_internal_jwt)) -> dict:
    response.status_code = 501
    return {"error": "not_implemented", "detail": "GET /catalog/version pending Wave 5"}
