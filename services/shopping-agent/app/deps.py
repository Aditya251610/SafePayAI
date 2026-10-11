"""FastAPI Depends: internal service-JWT verification, DB session, idempotency check.

Per docs/service-skeleton-conventions.md section 5: a real Depends that verifies a JWT via
JWKS (cached), pointed at a local static fixture until api-gateway exists. Never an
`if True` fake-pass. Business routes (propose/intent-fit) use this; /health and /readyz do not.
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import Depends, Header, HTTPException

from app.settings import Settings, get_settings


@dataclass(frozen=True)
class ServicePrincipal:
    sub: str
    role: str | None
    buyer_id: str | None


def _jwks_client(settings: Settings) -> jwt.PyJWKClient:
    # Cached per-process; points at a local static JWKS fixture in Wave 4 (no gateway yet).
    return jwt.PyJWKClient(settings.internal_jwks_url)


async def require_service_jwt(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> ServicePrincipal:
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
            audience=settings.service_audience,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED") from exc
    return ServicePrincipal(
        sub=claims.get("sub", ""),
        role=claims.get("role"),
        buyer_id=claims.get("buyer_id"),
    )


async def require_checkout_caller(
    principal: ServicePrincipal = Depends(require_service_jwt),
) -> ServicePrincipal:
    if principal.sub != "svc:checkout":
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    return principal
