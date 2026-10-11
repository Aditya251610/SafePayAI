"""FastAPI Depends: internal service-JWT verification, DB session, idempotency check.

Per docs/service-skeleton-conventions.md section 5: real JWT verification via JWKS, pointed
at a local static fixture until api-gateway exists. api.md section 1: buyer or service
callers; browser never calls checkout directly.
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import Depends, Header, HTTPException

from app.settings import Settings, get_settings


@dataclass(frozen=True)
class Principal:
    sub: str
    role: str | None
    buyer_id: str | None


def _jwks_client(settings: Settings) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(settings.internal_jwks_url)


async def require_service_jwt(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> Principal:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        jwks_client = _jwks_client(settings)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "EdDSA"],
            audience=settings.internal_jwt_audience,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED") from exc
    return Principal(
        sub=claims.get("sub", ""),
        role=claims.get("role"),
        buyer_id=claims.get("buyer_id"),
    )


async def require_idempotency_key(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> str:
    if not idempotency_key:
        raise HTTPException(status_code=422, detail="IDEMPOTENCY_KEY_REQUIRED")
    return idempotency_key
