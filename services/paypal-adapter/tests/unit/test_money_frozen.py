"""L1 unit tests for app.ops._money_frozen: the static-env-var OR DB-flag fail-closed logic
added this wave (either source freezing money ops is enough to block)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app import ops
from app.control_flags import ControlFlags
from app.settings import Settings


def _settings(money_enabled: bool) -> Settings:
    return Settings(money_enabled=money_enabled)


@pytest.mark.asyncio
async def test_static_flag_off_is_frozen_without_touching_db(monkeypatch):
    """When the static env var alone says disabled, _money_frozen must short-circuit and
    never hit the DB (session is a bare object -- any DB access would blow up)."""
    settings = _settings(money_enabled=False)
    assert await ops._money_frozen(settings, session=object()) is True  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_static_flag_on_and_db_frozen_false_is_not_frozen(monkeypatch):
    settings = _settings(money_enabled=True)
    monkeypatch.setattr(
        ops.control_flags,
        "get_control_flags",
        AsyncMock(return_value=ControlFlags(money_enabled=True, frozen=False, updated_at=None)),  # type: ignore[arg-type]
    )
    assert await ops._money_frozen(settings, session=object()) is False  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_static_flag_on_but_db_frozen_true_is_frozen(monkeypatch):
    """Either source freezing is enough to block (fail closed)."""
    settings = _settings(money_enabled=True)
    monkeypatch.setattr(
        ops.control_flags,
        "get_control_flags",
        AsyncMock(return_value=ControlFlags(money_enabled=True, frozen=True, updated_at=None)),  # type: ignore[arg-type]
    )
    assert await ops._money_frozen(settings, session=object()) is True  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_static_flag_on_but_db_row_missing_is_frozen(monkeypatch):
    """An absent/unreadable DB row is treated as frozen, not as 'no opinion'."""
    settings = _settings(money_enabled=True)
    monkeypatch.setattr(ops.control_flags, "get_control_flags", AsyncMock(return_value=None))
    assert await ops._money_frozen(settings, session=object()) is True  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_check_money_enabled_raises_money_frozen(monkeypatch):
    settings = _settings(money_enabled=False)
    with pytest.raises(ops.OpError) as exc_info:
        await ops._check_money_enabled(settings, session=object(), trace_id="tr1")  # type: ignore[arg-type]
    assert exc_info.value.code == "MONEY_FROZEN"
    assert exc_info.value.http_status == 403
