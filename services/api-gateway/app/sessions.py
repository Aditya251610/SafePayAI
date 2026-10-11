"""Session mechanics (spec.md section 4): cookie value, creation, validation, slide,
deletion, epoch checks. This module is infra - same lane as a JWT-verify helper
elsewhere - not business logic: it does not decide who may do what.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import CursorResult, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.settings import Settings

# Throttle for last_seen_at writes (spec.md section 4.1: "at most once per minute").
_SLIDE_THROTTLE_S = 60


def hash_sid(raw_sid: str) -> str:
    return hashlib.sha256(raw_sid.encode("utf-8")).hexdigest()


def generate_sid() -> str:
    """256-bit random, base64url (spec.md section 4.1)."""
    return secrets.token_urlsafe(32)


def ttl_seconds_for_role(role: str, settings: Settings) -> int:
    if role == "buyer":
        return settings.session_ttl_buyer_s
    return settings.session_ttl_staff_s


def cap_seconds_for_role(role: str, settings: Settings) -> int:
    if role == "buyer":
        return settings.session_cap_buyer_s
    return settings.session_ttl_staff_s


@dataclass(frozen=True)
class SessionRecord:
    sid_hash: str
    user_id: str
    role: str
    epoch: int
    actor_type: str
    display_name: str | None
    expires_at: datetime
    created_at: datetime


async def create_session(
    db: AsyncSession,
    *,
    user_id: str,
    role: str,
    epoch: int,
    settings: Settings,
    ip_hash: str | None = None,
    ua_hash: str | None = None,
) -> tuple[str, datetime]:
    """Creates a brand-new session row and returns (raw_sid, expires_at). Callers
    (login/demo-session) are responsible for deleting any previously-presented sid
    first (fixation, REQ-GW-003)."""
    raw_sid = generate_sid()
    sid_hash = hash_sid(raw_sid)
    ttl_s = ttl_seconds_for_role(role, settings)
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl_s)

    await db.execute(
        text(
            """
            INSERT INTO "gateway"."sessions"
                (sid_hash, user_id, role, epoch, created_at, last_seen_at, expires_at,
                 ip_hash, ua_hash)
            VALUES
                (:sid_hash, :user_id, :role, :epoch, now(), now(), :expires_at, :ip_hash, :ua_hash)
            """
        ),
        {
            "sid_hash": sid_hash,
            "user_id": user_id,
            "role": role,
            "epoch": epoch,
            "expires_at": expires_at,
            "ip_hash": ip_hash,
            "ua_hash": ua_hash,
        },
    )
    await db.commit()
    return raw_sid, expires_at


async def delete_session(db: AsyncSession, raw_sid: str | None) -> None:
    """No-op if raw_sid is falsy/unknown - deleting a session that doesn't exist is
    not an error (fixation cleanup and logout both call this)."""
    if not raw_sid:
        return
    sid_hash = hash_sid(raw_sid)
    await db.execute(
        text('DELETE FROM "gateway"."sessions" WHERE sid_hash = :sid_hash'),
        {"sid_hash": sid_hash},
    )
    await db.commit()


async def get_global_epoch(db: AsyncSession) -> int:
    row = (
        await db.execute(
            text('SELECT value FROM "gateway"."settings" WHERE key = \'global_epoch\'')
        )
    ).first()
    if row is None or row[0] is None:
        return 0
    try:
        return int(row[0])
    except ValueError:
        return 0


async def touch_session(db: AsyncSession, sid_hash: str) -> None:
    """Throttled sliding-expiry update: only writes if `last_seen_at` is more than
    `_SLIDE_THROTTLE_S` old, and never past the role's hard cap from creation."""
    await db.execute(
        text(
            """
            UPDATE "gateway"."sessions"
            SET last_seen_at = now()
            WHERE sid_hash = :sid_hash
              AND last_seen_at < now() - make_interval(secs => :throttle_s)
            """
        ),
        {"sid_hash": sid_hash, "throttle_s": _SLIDE_THROTTLE_S},
    )
    await db.commit()


async def bump_user_epoch(db: AsyncSession, user_id: str) -> None:
    await db.execute(
        text('UPDATE "gateway"."users" SET epoch = epoch + 1 WHERE id = :user_id'),
        {"user_id": user_id},
    )
    await db.commit()


async def purge_expired(db: AsyncSession) -> int:
    """Lazy purge of expired sessions and expired ephemeral buyers with no session
    left (spec.md section 4.2). Best-effort, called opportunistically; not wired to
    a scheduler in Wave 5."""
    result = await db.execute(
        text('DELETE FROM "gateway"."sessions" WHERE expires_at < now()')
    )
    await db.execute(
        text(
            """
            DELETE FROM "gateway"."users" u
            WHERE u.is_ephemeral = true
              AND NOT EXISTS (SELECT 1 FROM "gateway"."sessions" s WHERE s.user_id = u.id)
            """
        )
    )
    await db.commit()
    assert isinstance(result, CursorResult)
    return result.rowcount or 0


async def count_live_ephemeral_buyers(db: AsyncSession) -> int:
    row = (
        await db.execute(
            text(
                """
                SELECT count(*) FROM "gateway"."users" u
                WHERE u.is_ephemeral = true AND u.disabled_at IS NULL
                """
            )
        )
    ).first()
    return int(row[0]) if row else 0
