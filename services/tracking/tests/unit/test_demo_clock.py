"""Unit tests for app/domain/demo_clock.py (spec s3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app_tracking.domain.demo_clock import (
    DEMO_MIN_ADVANCE_SECONDS,
    DemoClockSnapshot,
    apply_advance,
    sim_now,
    validate_advance_delta,
)


def test_sim_now_with_zero_offset_returns_real_time() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert sim_now(now, 0) == now


def test_sim_now_adds_offset_seconds() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert sim_now(now, 3600) == now + timedelta(hours=1)


@pytest.mark.parametrize("delta", [0, -1, -100])
def test_validate_advance_delta_rejects_non_forward(delta: int) -> None:
    with pytest.raises(ValueError):
        validate_advance_delta(delta, 1000)


def test_validate_advance_delta_rejects_over_max() -> None:
    with pytest.raises(ValueError):
        validate_advance_delta(1001, 1000)


def test_validate_advance_delta_accepts_in_bounds() -> None:
    validate_advance_delta(DEMO_MIN_ADVANCE_SECONDS, 1000)
    validate_advance_delta(1000, 1000)


def test_apply_advance_increments_offset_and_version() -> None:
    snapshot = DemoClockSnapshot(offset_seconds=10, version=5)
    result = apply_advance(snapshot, 20)
    assert result.offset_seconds == 30
    assert result.version == 6
