"""Gateway-owned session endpoints (spec.md section 5.1 / api.md section 3).

Real argon2id verify, sliding-expiry sessions, `__Host-` cookie, and the in-process
rate limiter live here. CSRF token issuance (`GET /api/auth/csrf`) is real -- see
app/csrf.py for the full design (single-use, purpose-scoped, session-bound tokens
backed by `gateway.csrf_uses`).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import verify_password
from app.csrf import issue_csrf_token
from app.db import get_db_session
from app.deps import Principal, clear_session_cookie, require_session
from app.ratelimit import limiter
from app.schemas.auth import LoginRequest
from app.sessions import (
    count_live_ephemeral_buyers,
    create_session,
    delete_session,
)
from app.settings import Settings, get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Starting values (spec.md section 6.3 / C17: tune after load test; demo-grade).
AUTH_RATE_LIMIT = 10
AUTH_WINDOW_S = 60.0
AUTH_LOGIN_RATE_LIMIT = 5
AUTH_LOGIN_WINDOW_S = 60.0


def _client_ip(request: Request, settings: Settings) -> str:
    """Only trusts `X-Forwarded-For` up to `PS_APIGATEWAY_TRUSTED_PROXY_COUNT` hops
    (spec.md section 6.3 / REQ-GW-023); otherwise uses the direct peer address."""
    if settings.trusted_proxy_count > 0:
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            hops = [h.strip() for h in xff.split(",")]
            idx = max(0, len(hops) - settings.trusted_proxy_count)
            return hops[idx]
    client = request.client
    return client.host if client else "unknown"


def _set_session_cookie(
    response: Response, settings: Settings, raw_sid: str, expires_at: datetime
) -> None:
    response.set_cookie(
        key=settings.cookie_name,
        value=raw_sid,
        path="/",
        httponly=True,
        secure=True,
        samesite="lax",
        expires=expires_at,
    )


def _rate_limited(response: Response, retry_after: float) -> dict:
    response.status_code = 429
    response.headers["Retry-After"] = str(int(retry_after) + 1)
    return {
        "error": "RATE_LIMITED",
        "message": "Too many requests, try again later.",
        "request_id": str(uuid.uuid4()),
    }


@router.post("/demo-session", status_code=201)
async def demo_session(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    ip = _client_ip(request, settings)
    allowed, retry_after = limiter.check(f"auth:{ip}", AUTH_RATE_LIMIT, AUTH_WINDOW_S)
    if not allowed:
        return _rate_limited(response, retry_after)

    live_count = await count_live_ephemeral_buyers(db)
    if live_count >= settings.max_ephemeral_buyers:
        response.status_code = 503
        return {
            "error": "UPSTREAM_UNAVAILABLE",
            "message": "Demo is at capacity, try again shortly.",
            "request_id": str(uuid.uuid4()),
        }

    display_name = f"demo-buyer-{uuid.uuid4().hex[:8]}"
    row = (
        await db.execute(
            text(
                """
                INSERT INTO "gateway"."users"
                    (handle, role, actor_type, display_name, is_ephemeral, epoch)
                VALUES (NULL, 'buyer', 'buyer', :display_name, true, 0)
                RETURNING id, epoch
                """
            ),
            {"display_name": display_name},
        )
    ).first()
    await db.commit()
    if row is None:
        raise HTTPException(
            status_code=500, detail="failed to create demo session user"
        )
    user_id, epoch = str(row[0]), row[1]

    raw_sid, expires_at = await create_session(
        db, user_id=user_id, role="buyer", epoch=epoch, settings=settings
    )
    _set_session_cookie(response, settings, raw_sid, expires_at)

    return {
        "principal": {
            "actor_type": "buyer",
            "actor_id": user_id,
            "role": "buyer",
            "display_name": display_name,
        },
        "expires_at": expires_at.isoformat(),
    }


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    ps_sid: str | None = Cookie(default=None, alias="__Host-ps_sid"),
) -> dict:
    ip = _client_ip(request, settings)
    key = f"auth-login:{ip}:{body.handle}"
    allowed, retry_after = limiter.check(
        key, AUTH_LOGIN_RATE_LIMIT, AUTH_LOGIN_WINDOW_S
    )
    if not allowed:
        return _rate_limited(response, retry_after)

    row = (
        (
            await db.execute(
                text(
                    """
                SELECT id, role, actor_type, display_name, password_hash, epoch, disabled_at
                FROM "gateway"."users"
                WHERE handle = :handle AND is_ephemeral = false
                """
                ),
                {"handle": body.handle},
            )
        )
        .mappings()
        .first()
    )

    # Identical failure for unknown handle vs wrong password (REQ-GW-002, GW-U12,
    # GW-X03): always run verify_password, even against a dummy hash.
    password_hash = row["password_hash"] if row is not None else None
    ok = verify_password(body.password, password_hash)
    if row is None or not ok or row["disabled_at"] is not None:
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")

    # Fixation: delete any presented sid before issuing a new one (REQ-GW-003).
    await delete_session(db, ps_sid)

    user_id = str(row["id"])
    raw_sid, expires_at = await create_session(
        db, user_id=user_id, role=row["role"], epoch=row["epoch"], settings=settings
    )
    _set_session_cookie(response, settings, raw_sid, expires_at)

    return {
        "principal": {
            "actor_type": row["actor_type"],
            "actor_id": user_id,
            "role": row["role"],
            "display_name": row["display_name"],
        },
        "expires_at": expires_at.isoformat(),
    }


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    principal: Principal = Depends(require_session),
    ps_sid: str | None = Cookie(default=None, alias="__Host-ps_sid"),
) -> None:
    await delete_session(db, ps_sid)
    clear_session_cookie(response, settings)


@router.get("/me")
async def me(principal: Principal = Depends(require_session)) -> dict:
    expires_at = principal.session_expires_at
    return {
        "actor_type": principal.actor_type,
        "actor_id": principal.actor_id,
        "role": principal.role,
        "auth_method": "session",
        "display_name": principal.display_name,
        "session_expires_at": expires_at.isoformat()
        if isinstance(expires_at, datetime)
        else None,
    }


@router.get("/csrf")
async def csrf(
    purpose: str = "general",
    principal: Principal = Depends(require_session),
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    token, expires_at = await issue_csrf_token(
        db, sid_hash=principal.sid_hash, purpose=purpose, settings=settings
    )
    return {
        "csrf_token": token,
        "purpose": purpose,
        "expires_at": expires_at.isoformat(),
    }
