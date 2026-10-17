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

from app_mandate.db import get_db_session
from app_mandate.settings import Settings, get_settings

# Was a single hardcoded string, matching only api-gateway - ADR-006's documented
# design is "gateway is the sole minter", but checkout's app/deps.py already has its
# own mint_outbound_token (issuer="checkout") calling mandate directly in its
# capture/reservation flow (orders.py, carts.py), and shopping-agent now does the
# same (issuer="shopping-agent", for its /mandates/{id}/summary read). Neither ever
# actually verified here - found live, the first time any of these paths were
# exercised over a real network call rather than a test that overrides this
# dependency entirely. Both keys are published in api-gateway's JWKS (resolve
# the key, not the issuer claim, is the thing that actually proves identity, since
# PS_APIGATEWAY_PREVIOUS_PUBLIC_KEYS membership is what makes a key verifiable at
# all) - widening the issuer allowlist to match reconciles the two sides instead of
# ripping out checkout's already-built, already-used minting pattern.
TRUSTED_ISSUERS = frozenset({"api-gateway", "checkout", "shopping-agent"})


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
        parsed: dict[str, str] = json.loads(settings.trusted_issuers)
        return parsed
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
                token,
                key,
                algorithms=["EdDSA", "RS256"],
                audience=settings.internal_jwt_audience,
                options={"require": ["exp", "iss"]},
            )
        elif settings.internal_jwks_url:
            client = jwt.PyJWKClient(settings.internal_jwks_url)
            signing_key = client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["EdDSA", "RS256"],
                audience=settings.internal_jwt_audience,
                options={"require": ["exp", "iss"]},
            )
        else:
            raise HTTPException(
                status_code=401, detail="no trusted issuer configuration"
            )
        # Checked manually (not via jwt.decode's own `issuer=` kwarg) to avoid relying
        # on PyJWT version-specific support for a list/set there - unambiguous either way.
        if claims.get("iss") not in TRUSTED_ISSUERS:
            raise HTTPException(status_code=401, detail="untrusted issuer")
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


async def require_buyer(
    principal: Principal = Depends(verify_internal_jwt),
) -> Principal:
    if principal.role != "buyer":
        raise HTTPException(status_code=403, detail="ROLE_NOT_ALLOWED")
    return principal


async def require_service_caller(
    principal: Principal = Depends(verify_internal_jwt),
) -> Principal:
    if not principal.sub.startswith("svc:"):
        raise HTTPException(status_code=403, detail="CALLER_NOT_ALLOWED")
    return principal
