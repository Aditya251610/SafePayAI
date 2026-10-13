"""paypal.control_flags DB access: this service's own kill switch, separate from the static
PS_PAYPALADAPTER_MONEY_ENABLED env var (app.settings.Settings.money_enabled). Single row,
id=1, seeded frozen=true by migrations/versions/0001_baseline.py (mirrors resolution's own
control_flags seed in its 0001_baseline.py). svc_paypal only has SELECT/UPDATE on this table
(no INSERT) -- the row can only ever be created by a migration, never by this module.

Fail closed throughout (spec.md section 9): an absent/unreadable row is treated as frozen.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class ControlFlags:
    money_enabled: bool
    frozen: bool
    updated_at: datetime


async def get_control_flags(session: AsyncSession) -> ControlFlags | None:
    result = await session.execute(
        text("SELECT money_enabled, frozen, updated_at FROM paypal.control_flags WHERE id = 1")
    )
    row = result.mappings().first()
    if row is None:
        return None
    return ControlFlags(
        money_enabled=bool(row["money_enabled"]),
        frozen=bool(row["frozen"]),
        updated_at=row["updated_at"],
    )


async def set_frozen(session: AsyncSession, *, frozen: bool) -> ControlFlags | None:
    """Returns None if no row exists to update -- should not happen post-migration (the
    baseline migration seeds id=1); the router maps a None here to a 503 rather than
    silently reporting success for a write that did not actually happen."""
    result = await session.execute(
        text(
            "UPDATE paypal.control_flags SET frozen = :frozen, updated_at = now() "
            "WHERE id = 1 RETURNING money_enabled, frozen, updated_at"
        ),
        {"frozen": frozen},
    )
    row = result.mappings().first()
    await session.commit()
    if row is None:
        return None
    return ControlFlags(
        money_enabled=bool(row["money_enabled"]),
        frozen=bool(row["frozen"]),
        updated_at=row["updated_at"],
    )
