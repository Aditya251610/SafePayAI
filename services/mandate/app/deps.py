"""FastAPI Depends: DB session, internal-JWT auth verification, idempotency check.

Per mandate/spec.md section 12 C7: supports PS_MANDATE_TRUSTED_ISSUERS (static map,
preferred, no cold-start network dependency) or PS_MANDATE_INTERNAL_JWKS_URL.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

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
    scope: list[str] = field(default_factory=list)
    buyer_id: str | None = None


async def get_session(session: AsyncSession = Depends(get_db_session)) -> AsyncSession:
    return session


def _trusted_issuer_keys(settings: Settings) -> dict[str, str]:
    if not settings.trusted_issuers:
        return {}
    try:
        return json.loads(settings.trusted_issuers)
    except ValueError:
        return {}


async def verify_internal_jwt(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> Principal:
    """Verifies the internal service JWT minted by api-gateway (aud=mandate).

    Wave 4: real verification, fails closed (401) rather than an `if True` bypass.
    Prefers a static trusted-issuers map (no network dependency at cold start);
    falls back to a JWKS fetch if configured.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()

    issuer_keys = _trusted_issuer_keys(settings)
    try:
        if issuer_keys:
            unverified = jwt.get_unverified_header(token)
            kid = unverified.get("kid")
            key = issuer_keys.get(kid) if kid else None
            if key is None:
                raise HTTPException(status_code=401, detail="unknown signing key")
            claims = jwt.decode(
                token, key, algorithms=["EdDSA", "RS256"], audience=settings.internal_jwt_audience
            )
        elif settings.internal_jwks_url:
            client = jwt.PyJWKClient(settings.internal_jwks_url)
            signing_key = client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["EdDSA", "RS256"],
                audience=settings.internal_jwt_audience,
            )
        else:
            raise HTTPException(status_code=401, detail="no trusted issuer configuration")
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="invalid internal token") from exc

    act = claims.get("act") or {}
    return Principal(
        sub=claims.get("sub", ""),
        role=claims.get("role", act.get("role", "")),
        jti=claims.get("jti", ""),
        scope=claims.get("scope", []),
        buyer_id=act.get("actor_id"),
    )


async def require_buyer(principal: Principal = Depends(verify_internal_jwt)) -> Principal:
    if principal.role != "buyer":
        raise HTTPException(status_code=403, detail="ROLE_NOT_ALLOWED")
    return principal


async def require_service_caller(principal: Principal = Depends(verify_internal_jwt)) -> Principal:
    if not principal.sub.startswith("svc:"):
        raise HTTPException(status_code=403, detail="CALLER_NOT_ALLOWED")
    return principal
