"""FastAPI Depends: internal service-JWT verification, caller allowlist, ticket extraction.

Per docs/service-skeleton-conventions.md section 5 and api.md section 1/3: every call is
authenticated; money tools additionally require X-Authorization-Ticket. Mirrors mandate's
app/deps.py (spec.md C7 there): prefers a static PS_PAYPALADAPTER_INTERNAL_TRUSTED_ISSUERS
map (kid -> PEM/secret, no network dependency at cold start / in tests), falls back to a
JWKS fetch at PS_PAYPALADAPTER_INTERNAL_JWKS_URL if configured. Wave 5B wires real
verification for orders/captures. Full HMAC authorization-ticket verification (spec.md
section 5) is now real too (`verify_authorization_ticket` below): the HMAC key is selected
by the caller's own already-verified JWT identity (never by a client-supplied kid embedded
in the ticket itself -- that would let a caller pick which key verifies its own ticket),
bound to the exact money fields of the request (mandate_id, proposal_hash, amount_minor,
currency) plus the expiry embedded in the ticket.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Depends, Header, HTTPException
from safepayai_common.auth.ticket import TicketPayload, verify_ticket

from app.settings import Settings, get_settings

DEFAULT_ALLOWLIST: dict[str, set[str]] = {
    "create_order": {"checkout", "svc:checkout"},
    "capture_order": {"checkout", "svc:checkout"},
    "refund_capture": {"resolution", "svc:resolution"},
    "get_order": {
        "checkout",
        "svc:checkout",
        "tracking",
        "svc:tracking",
        "resolution",
        "svc:resolution",
    },
    "get_capture": {
        "checkout",
        "svc:checkout",
        "tracking",
        "svc:tracking",
        "resolution",
        "svc:resolution",
    },
    "get_refund": {"resolution", "svc:resolution"},
    "add_tracking": {"tracking", "svc:tracking"},
    "get_tracking": {"tracking", "svc:tracking", "resolution", "svc:resolution"},
    "cancel_tracking": {"tracking", "svc:tracking"},
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


class _AuthUnavailable(Exception):
    """Internal signal: no verification key material configured at all (503, not 401)."""


def verify_internal_jwt(token: str, settings: Settings) -> dict[str, Any] | None:
    """Shared verification used by both the REST dependency below and the MCP handler
    (app/mcp.py `_extract_caller`) -- one code path for caller identity, same dual-mode
    support (static trusted-issuer map first, JWKS fallback) in both places. Returns the
    decoded claims, or None on any verification failure (including "no key material
    configured" -- 401, treated the same as "invalid" from a caller's perspective; MCP has
    no 503 semantics to distinguish it)."""
    issuer_keys = _trusted_issuer_keys(settings)
    try:
        if issuer_keys:
            unverified = jwt.get_unverified_header(token)
            kid = unverified.get("kid")
            key = issuer_keys.get(kid) if kid else None
            if key is None:
                return None
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
            raise _AuthUnavailable
    except jwt.PyJWTError:
        return None
    return dict(claims)


async def require_internal_jwt(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> Caller:
    """Deny by default: missing/invalid token, unknown kid, wrong aud/exp -> 401."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        claims = verify_internal_jwt(token, settings)
    except _AuthUnavailable as exc:
        raise HTTPException(status_code=503, detail="UPSTREAM_AUTH_FAILED") from exc
    if claims is None:
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")
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


def _ticket_key_for_caller(caller_sub: str, settings: Settings) -> tuple[bytes, str] | None:
    """Key selection is by the caller's own verified JWT identity ONLY -- the ticket's own
    embedded kid is never trusted to pick which key verifies it (that would let a caller
    choose its own verifier). Returns None if that caller has no ticket key provisioned."""
    if caller_sub in ("checkout", "svc:checkout"):
        if settings.checkout_ticket_hmac_key:
            return settings.checkout_ticket_hmac_key.encode(), (
                settings.checkout_ticket_hmac_kid or "k1"
            )
        return None
    if caller_sub in ("resolution", "svc:resolution"):
        if settings.resolution_ticket_hmac_key:
            return settings.resolution_ticket_hmac_key.encode(), (
                settings.resolution_ticket_hmac_kid or "k1"
            )
        return None
    return None


def authorization_ticket_is_valid(
    token: str,
    *,
    caller_sub: str,
    mandate_id: str,
    proposal_hash: str,
    amount_minor: int,
    currency: str,
    settings: Settings,
) -> bool:
    """Pure boolean form of the real HMAC verification (spec.md section 5), shared by the
    REST wrapper below (raises HTTPException) and the MCP dispatcher (raises OpError) --
    one check, two error envelopes. False for any failure: no key provisioned for this
    caller, malformed token, expired, or bad signature -- deliberately not distinguished
    (no enumeration of which check failed)."""
    key_and_kid = _ticket_key_for_caller(caller_sub, settings)
    if key_and_kid is None:
        return False
    key, _expected_kid = key_and_kid

    parts = token.split(".", 2)
    if len(parts) != 3:
        return False
    _kid, exp_s, _digest = parts
    try:
        expires_at = int(exp_s)
    except ValueError:
        return False

    payload = TicketPayload(
        mandate_id=mandate_id,
        proposal_hash=proposal_hash,
        amount_minor=amount_minor,
        currency=currency,
        expires_at=expires_at,
    )
    return verify_ticket(token, payload, key)


def verify_authorization_ticket(
    token: str,
    *,
    caller_sub: str,
    mandate_id: str,
    proposal_hash: str,
    amount_minor: int,
    currency: str,
    settings: Settings,
) -> None:
    """REST wrapper: raises HTTPException(403, TICKET_INVALID) if the ticket doesn't verify."""
    if not authorization_ticket_is_valid(
        token,
        caller_sub=caller_sub,
        mandate_id=mandate_id,
        proposal_hash=proposal_hash,
        amount_minor=amount_minor,
        currency=currency,
        settings=settings,
    ):
        raise HTTPException(status_code=403, detail="TICKET_INVALID")
