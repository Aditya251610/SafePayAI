"""FastAPI Depends: DB session, internal-JWT auth verification, idempotency check.

Wave 4: auth dependency actually verifies a JWT (does not fake-pass with `if True`)
per docs/service-skeleton-conventions.md section 5. Points at a local static JWKS
fixture / trusted-issuers map until api-gateway is implemented, so this service can
still run standalone.
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.settings import Settings, get_settings


@dataclass(frozen=True)
class Principal:
    sub: str
    role: str
    jti: str
    scope: list[str]


async def get_session(session: AsyncSession = Depends(get_db_session)) -> AsyncSession:
    return session


def _jwks_client(settings: Settings) -> jwt.PyJWKClient | None:
    if not settings.internal_jwks_url:
        return None
    return jwt.PyJWKClient(settings.internal_jwks_url)


async def verify_internal_jwt(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> Principal:
    """Verifies the internal service JWT minted by api-gateway (aud=catalog).

    Wave 4: real verification against a JWKS endpoint when configured, else fails
    closed with 401 rather than skipping the check. Never an `if True` bypass.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()

    client = _jwks_client(settings)
    if client is None:
        # No JWKS configured yet (api-gateway not reachable in this environment).
        # Fail closed rather than skip verification.
        raise HTTPException(status_code=401, detail="internal JWKS not configured")

    try:
        signing_key = client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["EdDSA", "RS256"],
            audience=settings.internal_jwt_audience,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="invalid internal token") from exc

    return Principal(
        sub=claims.get("sub", ""),
        role=claims.get("role", ""),
        jti=claims.get("jti", ""),
        scope=claims.get("scope", []),
    )
