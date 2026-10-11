"""FastAPI Depends: DB session, internal-JWT auth verification, idempotency check.

Wave 4: auth dependency actually verifies a JWT (does not fake-pass with `if True`)
per docs/service-skeleton-conventions.md section 5. Points at a local static JWKS
fixture / trusted-issuers map until api-gateway is implemented, so this service can
still run standalone.
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.errors import CatalogError
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
        raise CatalogError(401, "UNAUTHENTICATED", "missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()

    client = _jwks_client(settings)
    if client is None:
        # No JWKS configured yet (api-gateway not reachable in this environment).
        # Fail closed rather than skip verification.
        raise CatalogError(401, "UNAUTHENTICATED", "internal JWKS not configured")

    try:
        signing_key = client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["EdDSA", "RS256"],
            audience=settings.internal_jwt_audience,
        )
    except jwt.PyJWTError as exc:
        raise CatalogError(401, "UNAUTHENTICATED", "invalid internal token") from exc

    return Principal(
        sub=claims.get("sub", ""),
        role=claims.get("role", ""),
        jti=claims.get("jti", ""),
        scope=claims.get("scope", []),
    )


# Wave 5 scope note (flagged decision, not implemented here): spec.md section 10's
# caller allowlist (e.g. "/prices/resolve: checkout, shopping-agent, gateway BFF") is
# NOT enforced per-role in this wave. api-gateway does not exist yet, so the exact
# role strings it will mint are undecided (spec.md C4: "gateway must mint operator
# role or map it"). Guessing role spelling now risks silently locking out legitimate
# callers once the gateway contract lands. Every route below only requires a valid
# internal JWT (`verify_internal_jwt`); a `require_roles(*allowed)` dependency factory
# is the natural place to add this once api-gateway's role contract is fixed.
