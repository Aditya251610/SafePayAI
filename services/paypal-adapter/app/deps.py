"""FastAPI Depends: internal service-JWT verification, caller allowlist, ticket extraction.

Per docs/service-skeleton-conventions.md section 5 and api.md section 1/3: every call is
authenticated; money tools additionally require X-Authorization-Ticket. Mirrors mandate's
app/deps.py (spec.md C7 there): prefers a static PS_PAYPALADAPTER_INTERNAL_TRUSTED_ISSUERS
map (kid -> PEM/secret, no network dependency at cold start / in tests), falls back to a
JWKS fetch at PS_PAYPALADAPTER_INTERNAL_JWKS_URL if configured. Wave 5B wires real
verification for orders/captures; full HMAC authorization-ticket verification (spec.md
section 5) is out of scope here (S2/S3, needs checkout/resolution minters) -- this module
only checks the ticket header is present, matching the Wave 4 stub behavior.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

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


def _trusted_issuer_keys(settings: Settings) -> dict[str, str]:
    if not settings.internal_trusted_issuers:
        return {}
    try:
        parsed: dict[str, str] = json.loads(settings.internal_trusted_issuers)
        return parsed
    except ValueError:
        return {}


async def require_internal_jwt(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> Caller:
    """Deny by default: missing/invalid token, unknown kid, wrong aud/exp -> 401."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")
    token = authorization.removeprefix("Bearer ").strip()

    issuer_keys = _trusted_issuer_keys(settings)
    try:
        if issuer_keys:
            unverified = jwt.get_unverified_header(token)
            kid = unverified.get("kid")
            key = issuer_keys.get(kid) if kid else None
            if key is None:
                raise HTTPException(status_code=401, detail="UNAUTHENTICATED")
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256", "EdDSA", "HS256"],
                audience=settings.internal_jwt_aud,
            )
        elif settings.internal_jwks_url:
            jwks_client = jwt.PyJWKClient(settings.internal_jwks_url)
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "EdDSA"],
                audience=settings.internal_jwt_aud,
            )
        else:
            raise HTTPException(status_code=503, detail="UPSTREAM_AUTH_FAILED")
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED") from exc
    return Caller(sub=claims.get("sub", ""))


def require_tool_permission(tool: str) -> Any:
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
