"""FastAPI Depends: db session, internal JWT verification, idempotency check.

Wave 4: real verification via libs/common's auth.jwt helpers, static JWKS fixture until
the gateway exists (conventions doc section 5). resolution issues its own tokens to the
adapter (scope money.execute) — minting is Wave 5; here we only verify inbound tokens.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

import jwt
from fastapi import Depends, Header, HTTPException, status
from safepayai_common.auth.jwt import verify_service_token
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.settings import settings


async def db_session(
    session: AsyncSession = Depends(get_session),
) -> AsyncIterator[AsyncSession]:
    yield session


def _jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient("https://localhost/.well-known/jwks.json")


async def require_internal_jwt(
    authorization: str | None = Header(default=None),
) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token"
        )
    token = authorization.removeprefix("Bearer ")
    trusted_issuers = (
        settings.internal_jwt_trusted_issuers.split(",")
        if settings.internal_jwt_trusted_issuers
        else []
    )
    try:
        claims = verify_service_token(
            token,
            jwks_client=_jwks_client(),
            audience="resolution",
            trusted_issuers=trusted_issuers,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=f"invalid token: {exc}"
        ) from exc
    return claims


def require_idempotency_key(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> str:
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="IDEMPOTENCY_KEY_REQUIRED"
        )
    return idempotency_key


def require_tick_secret(
    x_tick_secret: str | None = Header(default=None, alias="X-Tick-Secret"),
) -> None:
    import hmac

    if not x_tick_secret or not settings.tick_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid tick secret"
        )
    if not hmac.compare_digest(x_tick_secret, settings.tick_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid tick secret"
        )


def role_required(*roles: str) -> Callable[..., Any]:
    """Returns a dependency asserting claims.act.role is one of `roles`. Wave 4: wired, not
    exercised yet since all mutating routes 501 before reaching business logic."""

    async def _check(claims: dict = Depends(require_internal_jwt)) -> dict:
        role = (claims.get("act") or {}).get("role")
        if roles and role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="ROLE_NOT_ALLOWED"
            )
        return claims

    return _check
