"""FastAPI Depends: db session, internal JWT verification restricted to caller `resolution`.

Per api.md section 0 / spec.md section 1: inbound caller allowlist is `resolution` only;
missing/invalid/expired/wrong-aud -> 401 UNAUTHENTICATED; valid token but wrong caller ->
403 FORBIDDEN_CALLER. No outbound calls to other services from this FILE. ADR-010's actual
constraint is no PayPal credentials and no money-table DB access, not zero outbound calls
anywhere -- auth-gateway.md section 3.2's matrix explicitly allows `triage -> audit` for
this service's own outbox events (see app/routers/internal.py), the same narrow exception
shopping-agent (the other ADR-010 LLM-key holder) already has.
"""

from __future__ import annotations

import jwt
from fastapi import Header, HTTPException, status
from safepayai_common.auth.jwt import verify_service_token

from app_triage_ai.settings import settings


def _jwks_client() -> jwt.PyJWKClient:
    url = settings.internal_jwks_url or "https://localhost/.well-known/jwks.json"
    return jwt.PyJWKClient(url)


async def require_resolution_caller(
    authorization: str | None = Header(default=None),
) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="UNAUTHENTICATED"
        )
    token = authorization.removeprefix("Bearer ")
    try:
        claims = verify_service_token(
            token,
            jwks_client=_jwks_client(),
            audience=settings.internal_jwt_audience,
            trusted_issuers=["api-gateway", "resolution"],
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="UNAUTHENTICATED"
        ) from exc

    allowed_callers = {
        c.strip() for c in settings.internal_allowed_callers.split(",") if c.strip()
    }
    caller = claims.get("sub")
    if allowed_callers and caller not in allowed_callers:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN_CALLER"
        )
    return claims
