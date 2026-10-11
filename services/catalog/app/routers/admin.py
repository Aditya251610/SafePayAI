"""POST /admin/seed, POST /admin/reset, GET /admin/fixtures - stubs per catalog/api.md.

Role `operator` + PS_CATALOG_ADMIN_ENABLED flag required (Wave 5; not enforced
beyond auth in Wave 4 since there is no business logic yet).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.deps import Principal, verify_internal_jwt

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/seed")
async def admin_seed(
    response: Response, principal: Principal = Depends(verify_internal_jwt)
) -> dict:
    response.status_code = 501
    return {"error": "not_implemented", "detail": "POST /admin/seed pending Wave 5"}


@router.post("/reset")
async def admin_reset(
    response: Response, principal: Principal = Depends(verify_internal_jwt)
) -> dict:
    response.status_code = 501
    return {"error": "not_implemented", "detail": "POST /admin/reset pending Wave 5"}


@router.get("/fixtures")
async def admin_fixtures(
    response: Response, principal: Principal = Depends(verify_internal_jwt)
) -> dict:
    response.status_code = 501
    return {"error": "not_implemented", "detail": "GET /admin/fixtures pending Wave 5"}
