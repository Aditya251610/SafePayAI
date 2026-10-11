"""FastAPI dependencies: DB session and internal service-JWT verification.

Per service-skeleton-conventions.md sec 5: auth must be a real Depends that actually
verifies a JWT, not an `if True` stub. Audit's own spec.md sec 5/8 defines a static
trusted-issuer key map (no network JWKS fetch -- the chain-of-custody doc explicitly
calls this out as a deliberate difference from a live JWKS endpoint), so this module
verifies against PS_AUDIT_TRUSTED_ISSUERS (inline JSON or a file path) and falls back to
app/auth_fixtures/local_jwks.json for standalone runs before the gateway exists.

Wave 4 scope: signature/aud/exp verification and claim extraction only. The producer/
actor-type allowlist check (spec.md sec 5 step 4c/4d) is business logic and lands with
the route implementations in Wave 5.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jwt
from fastapi import Depends, Header, HTTPException, status

from app.settings import Settings, get_settings

_FIXTURE_PATH = Path(__file__).parent / "auth_fixtures" / "local_jwks.json"


@dataclass(frozen=True)
class ProducerClaims:
    """Verified claims from an internal service JWT (producer or gateway-minted)."""

    sub: str
    aud: str
    act: dict[str, Any] | None
    request_id: str | None
    trace_id: str | None


def _load_trusted_issuers(settings: Settings) -> dict[str, dict[str, dict[str, str]]]:
    raw = settings.trusted_issuers
    if raw:
        candidate = Path(raw)
        if candidate.exists():
            return json.loads(candidate.read_text())
        return json.loads(raw)
    if _FIXTURE_PATH.exists():
        data = json.loads(_FIXTURE_PATH.read_text())
        data.pop("_comment", None)
        return data
    return {}


def _find_key(issuers: dict[str, dict[str, dict[str, str]]], kid: str | None) -> dict[str, str] | None:
    if kid is None:
        return None
    for issuer_keys in issuers.values():
        if kid in issuer_keys:
            return issuer_keys[kid]
    return None


async def verify_internal_token(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> ProducerClaims:
    """Verifies the `Authorization: Bearer <jwt>` header.

    Used both for producer ingestion (`aud=audit`, `sub=<producer-slug>`, api.md sec 1)
    and for gateway-minted reads (api.md sec 0 "internal JWT minted by gateway carrying
    `act`"). Both surfaces share the same static trusted-issuer verification mechanism
    in Wave 4; Wave 5 may split this into two dependencies if the claim shapes diverge.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "unauthenticated", "message": "missing bearer token"},
        )
    token = authorization.split(" ", 1)[1].strip()

    issuers = _load_trusted_issuers(settings)
    if not issuers:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "unauthenticated", "message": "no trusted issuers configured"},
        )

    try:
        unverified_header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "unauthenticated", "message": "malformed token"},
        ) from exc

    key_entry = _find_key(issuers, unverified_header.get("kid"))
    if key_entry is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "unauthenticated", "message": "unknown key id"},
        )

    try:
        claims = jwt.decode(
            token,
            key_entry["public_key"],
            algorithms=[key_entry.get("alg", "RS256")],
            audience=settings.internal_audience,
            options={"require": ["exp", "sub", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "unauthenticated", "message": "token verification failed"},
        ) from exc

    return ProducerClaims(
        sub=claims["sub"],
        aud=claims["aud"],
        act=claims.get("act"),
        request_id=claims.get("req") or claims.get("request_id"),
        trace_id=claims.get("trace_id"),
    )
