"""FastAPI Depends: db session, internal service-JWT verification, idempotency check.

Wave 4: real verification wired against libs/common's auth.jwt helpers, pointed at a local
static JWKS fixture when the gateway isn't up yet (conventions doc section 5). No business
logic beyond auth/plumbing.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

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
    url = settings.internal_jwks_url or "https://localhost/.well-known/jwks.json"
    return jwt.PyJWKClient(url)


async def require_internal_jwt(
    authorization: str | None = Header(default=None),
) -> dict:
    """Verifies the internal service-JWT. Fails closed (401) on any error — never an `if True` stub."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token"
        )
    token = authorization.removeprefix("Bearer ")
    try:
        claims = verify_service_token(
            token,
            jwks_client=_jwks_client(),
            audience=settings.internal_audience,
            trusted_issuers=["api-gateway", "resolution"],
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
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header required",
        )
    return idempotency_key


def require_tick_secret(
    x_tick_secret: str | None = Header(default=None, alias="X-Tick-Secret"),
) -> None:
    import hmac

    if not x_tick_secret or not settings.internal_tick_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid tick secret"
        )
    if not hmac.compare_digest(x_tick_secret, settings.internal_tick_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid tick secret"
        )
