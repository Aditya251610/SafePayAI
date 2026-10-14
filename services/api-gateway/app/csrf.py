"""CSRF token issuance and consumption against `gateway.csrf_uses` (migration
0001_baseline.py: `jti uuid PK, sid_hash text, purpose text, expires_at timestamptz`,
grants SELECT/INSERT/DELETE only -- no UPDATE, since a token is never mutated, only
issued once and consumed (deleted) once).

Single-use, purpose-scoped, session-bound synchronizer tokens: `GET /api/auth/csrf`
issues a fresh token tied to the caller's own session (sid_hash) and a purpose string;
`require_csrf(purpose)` consumes it on the state-changing request that follows,
rejecting any token that doesn't exist, is expired, was issued to a different purpose,
or was issued to a different session. The row is deleted on both success (consumed,
can't be replayed) and failure (fail closed -- an invalid attempt doesn't leave a stale
row for a retry to exploit race conditions against).

`/api/auth/login`, `/api/auth/demo-session`, and `/api/auth/csrf` itself are
deliberately NOT behind this check -- there is no session yet (login/demo-session) or
it would be circular (csrf issuance). `/api/auth/logout` is also exempt: logging a
victim out is not a meaningful CSRF target (no state an attacker gains from it), and
every other `/api/auth/*` route only ever reads or creates a session, never acts on
money or another party's data.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Depends, Header, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.deps import Principal, require_session
from app.settings import Settings

DEFAULT_PURPOSE = "general"


async def issue_csrf_token(
    session: AsyncSession, *, sid_hash: str, purpose: str, settings: Settings
) -> tuple[str, datetime]:
    jti = uuid.uuid4()
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.csrf_ttl_s)
    await session.execute(
        text(
            """
            INSERT INTO "gateway"."csrf_uses" (jti, sid_hash, purpose, expires_at)
            VALUES (:jti, :sid_hash, :purpose, :expires_at)
            """
        ),
        {
            "jti": jti,
            "sid_hash": sid_hash,
            "purpose": purpose,
            "expires_at": expires_at,
        },
    )
    await session.commit()
    return str(jti), expires_at


def require_csrf(purpose: str = DEFAULT_PURPOSE) -> Any:
    """Dependency factory, same style as app.deps's role guards -- apply
    `Depends(require_csrf())` (default purpose) or `Depends(require_csrf("checkout"))`
    to any state-changing route. Must come after the route's own auth dependency so
    `principal` is already resolved (a 401 for no session should fire before a 403 for
    a bad/missing CSRF token)."""

    async def _check(
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        principal: Principal = Depends(require_session),
        session: AsyncSession = Depends(get_db_session),
    ) -> None:
        if not x_csrf_token:
            raise HTTPException(status_code=403, detail="CSRF_INVALID")
        try:
            jti = uuid.UUID(x_csrf_token)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail="CSRF_INVALID") from exc

        row = (
            (
                await session.execute(
                    text(
                        """
                        DELETE FROM "gateway"."csrf_uses" WHERE jti = :jti
                        RETURNING sid_hash, purpose, expires_at
                        """
                    ),
                    {"jti": jti},
                )
            )
            .mappings()
            .first()
        )
        await session.commit()

        if row is None:
            raise HTTPException(status_code=403, detail="CSRF_INVALID")

        expires_at = row["expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)

        if (
            row["sid_hash"] != principal.sid_hash
            or row["purpose"] != purpose
            or expires_at < datetime.now(UTC)
        ):
            raise HTTPException(status_code=403, detail="CSRF_INVALID")

    return _check
