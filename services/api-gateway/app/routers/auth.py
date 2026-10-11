"""Gateway-owned session endpoints - stubs per spec.md section 5.1 / api.md section 3.

Request validation uses the real pydantic schemas; session/cookie business logic
(argon2id verify, sliding expiry, csrf token issuance) is Wave 5.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.deps import Principal, require_session
from app.schemas.auth import LoginRequest

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _not_implemented(response: Response, path: str) -> dict:
    response.status_code = 501
    return {"error": "not_implemented", "detail": f"{path} pending Wave 5"}


@router.post("/demo-session")
async def demo_session(response: Response) -> dict:
    return _not_implemented(response, "POST /api/auth/demo-session")


@router.post("/login")
async def login(body: LoginRequest, response: Response) -> dict:
    return _not_implemented(response, "POST /api/auth/login")


@router.post("/logout")
async def logout(response: Response, principal: Principal = Depends(require_session)) -> dict:
    return _not_implemented(response, "POST /api/auth/logout")


@router.get("/me")
async def me(response: Response, principal: Principal = Depends(require_session)) -> dict:
    return _not_implemented(response, "GET /api/auth/me")


@router.get("/csrf")
async def csrf(
    response: Response, purpose: str = "general", principal: Principal = Depends(require_session)
) -> dict:
    return _not_implemented(response, "GET /api/auth/csrf")
