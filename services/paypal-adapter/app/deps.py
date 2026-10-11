"""FastAPI Depends: internal service-JWT verification, caller allowlist, ticket extraction.

Per docs/service-skeleton-conventions.md section 5 and api.md section 1/3: every call is
authenticated; money tools additionally require X-Authorization-Ticket. This module wires
verification using safepayai_common.auth.ticket.verify_ticket (import, don't reimplement)
but Wave 4 routes never reach the point of calling PayPal -- they return 501 after auth.
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import Depends, Header, HTTPException

from app.settings import Settings, get_settings

DEFAULT_ALLOWLIST: dict[str, set[str]] = {
    "create_order": {"checkout"},
    "capture_order": {"checkout"},
    "refund_capture": {"resolution"},
    "get_order": {"checkout", "tracking", "resolution"},
    "get_capture": {"checkout", "tracking", "resolution"},
    "get_refund": {"resolution"},
    "add_tracking": {"tracking"},
    "get_tracking": {"tracking", "resolution"},
}


@dataclass(frozen=True)
class Caller:
    sub: str  # e.g. "checkout", "tracking", "resolution"


def _jwks_client(settings: Settings) -> jwt.PyJWKClient | None:
    if not settings.internal_jwks_url:
        return None
    return jwt.PyJWKClient(settings.internal_jwks_url)


async def require_internal_jwt(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> Caller:
    """Real verification wired against a local static JWKS fixture (conventions doc section 5)
    until api-gateway exists. Deny by default: missing/invalid token -> 401."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")
    token = authorization.removeprefix("Bearer ").strip()
    jwks_client = _jwks_client(settings)
    if jwks_client is None:
        raise HTTPException(status_code=503, detail="UPSTREAM_AUTH_FAILED")
    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "EdDSA"],
            audience=settings.internal_jwt_aud,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED") from exc
    return Caller(sub=claims.get("sub", ""))


def require_tool_permission(tool: str):
    async def _dep(caller: Caller = Depends(require_internal_jwt)) -> Caller:
        allowed = DEFAULT_ALLOWLIST.get(tool, set())
        if caller.sub not in allowed:
            raise HTTPException(status_code=403, detail="NOT_PERMITTED")
        return caller

    return _dep


async def require_authorization_ticket(
    x_authorization_ticket: str | None = Header(default=None, alias="X-Authorization-Ticket"),
) -> str:
    if not x_authorization_ticket:
        raise HTTPException(status_code=403, detail="TICKET_INVALID")
    return x_authorization_ticket
