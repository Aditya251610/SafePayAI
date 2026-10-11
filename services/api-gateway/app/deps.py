"""FastAPI Depends: DB session, session-cookie auth, role checks.

api-gateway is the auth-issuing service (spec.md section 4): it terminates buyer/
merchant/operator sessions itself via a cookie, rather than verifying an internal
JWT minted elsewhere. This dependency does the real cookie -> hash -> DB lookup
(fail closed on missing/expired/unknown), which is the auth-mechanics equivalent of
JWT verification in the other services - not product/business logic.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.sessions import hash_sid
from app.settings import Settings, get_settings


@dataclass(frozen=True)
class Principal:
    actor_type: str
    actor_id: str
    role: str
    epoch: int
    display_name: str | None = None


async def get_session(session: AsyncSession = Depends(get_db_session)) -> AsyncSession:
    return session


async def require_session(
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    ps_sid: str | None = Cookie(default=None, alias="__Host-ps_sid"),
) -> Principal:
    """Resolves the session cookie to a Principal. Fails closed (401) on anything
    missing, expired, or not found - never an `if True` bypass. The actual cookie
    name is configurable (PS_APIGATEWAY_COOKIE_NAME); the FastAPI Cookie() alias
    above covers the documented default and Wave 5 can parametrize it further.
    """
    if not ps_sid:
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")

    sid_hash = hash_sid(ps_sid)
    row = (
        await session.execute(
            text(
                """
                SELECT s.user_id, s.role, s.epoch, s.expires_at, u.actor_type, u.display_name, u.disabled_at
                FROM "gateway"."sessions" s
                JOIN "gateway"."users" u ON u.id = s.user_id
                WHERE s.sid_hash = :sid_hash
                """
            ),
            {"sid_hash": sid_hash},
        )
    ).mappings().first()

    if row is None or row["disabled_at"] is not None:
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")

    return Principal(
        actor_type=row["actor_type"],
        actor_id=str(row["user_id"]),
        role=row["role"],
        epoch=row["epoch"],
        display_name=row["display_name"],
    )


async def require_buyer(principal: Principal = Depends(require_session)) -> Principal:
    if principal.role != "buyer":
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    return principal


async def require_merchant(principal: Principal = Depends(require_session)) -> Principal:
    if principal.role != "merchant":
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    return principal


async def require_operator(principal: Principal = Depends(require_session)) -> Principal:
    if principal.role != "operator":
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    return principal


async def require_staff(principal: Principal = Depends(require_session)) -> Principal:
    if principal.role not in ("merchant", "operator"):
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    return principal
