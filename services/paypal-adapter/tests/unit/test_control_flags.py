"""L1 unit tests for app.control_flags: fail-closed read ("no row" -> None, mapped by the
router to frozen=true) and the UPDATE-only write path (svc_paypal has no INSERT grant on
control_flags, see migrations/versions/0001_baseline.py's seed + grant comment)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.control_flags import ControlFlags, get_control_flags, set_frozen


def _session_returning(row: dict | None) -> MagicMock:
    session = MagicMock()
    result = MagicMock()
    result.mappings.return_value.first.return_value = row
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_get_control_flags_returns_none_when_row_missing():
    session = _session_returning(None)
    flags = await get_control_flags(session)
    assert flags is None


@pytest.mark.asyncio
async def test_get_control_flags_maps_row():
    now = datetime(2026, 10, 14, 12, 0, 0)
    session = _session_returning({"money_enabled": True, "frozen": False, "updated_at": now})
    flags = await get_control_flags(session)
    assert flags == ControlFlags(money_enabled=True, frozen=False, updated_at=now)


@pytest.mark.asyncio
async def test_set_frozen_returns_none_when_no_row_to_update():
    session = _session_returning(None)
    flags = await set_frozen(session, frozen=True)
    assert flags is None
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_frozen_returns_updated_row():
    now = datetime(2026, 10, 14, 12, 0, 0)
    session = _session_returning({"money_enabled": False, "frozen": True, "updated_at": now})
    flags = await set_frozen(session, frozen=True)
    assert flags == ControlFlags(money_enabled=False, frozen=True, updated_at=now)
