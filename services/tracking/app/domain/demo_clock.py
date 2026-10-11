"""Demo-clock types and pure time math for the SIMULATED CARRIER (tracking-owned time).

Implements tracking/spec.md section 3 (demo-clock semantics), section 8 (advance/reset bounds)
and REQ-TR-016 (reset). Pure module: `sim_now` takes the real UTC time as an argument instead
of reading a clock. Scaffold only; bodies are yours.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# Singleton row id in demo_clock (spec s2 tables: demo_clock(id=1, ...)).
DEMO_CLOCK_ROW_ID: int = 1

# Lower bound for advance(delta) (spec s8 item 6: delta between 1 and MAX).
DEMO_MIN_ADVANCE_SECONDS: int = 1

# Defaults mirror app/settings.py; the live values come from PS_TRACKING_DEMO_* env (TBD values, I).
DEMO_MAX_ADVANCE_SECONDS_DEFAULT: int = 2_592_000  # 30 days (I)
DEMO_MAX_ACTIONS_PER_MINUTE_DEFAULT: int = 30  # (I)

# Reset is the ONLY backwards move; it always lands on offset 0 (spec s3).
DEMO_RESET_OFFSET_SECONDS: int = 0


@dataclass(frozen=True, slots=True)
class DemoClockSnapshot:
    """Current row of demo_clock as read inside a transaction (spec s2, s3)."""

    offset_seconds: int  # >= 0 in practice; forward-only except reset
    version: int  # optimistic CAS counter; advance does WHERE version = :expected


@dataclass(frozen=True, slots=True)
class ClockAdvanceResult:
    """Outcome of one applied advance (api.md POST /demo/clock/advance 200 body, minus tick)."""

    from_sim: datetime
    to_sim: datetime
    version: int  # version AFTER the CAS update


@dataclass(frozen=True, slots=True)
class ClockJumpRecord:
    """One row of clock_jumps: the idempotent record of a single advance or reset (spec s2)."""

    idempotency_key: str  # unique; replay returns the stored result
    from_sim: datetime
    to_sim: datetime
    actor_sub: str  # JWT sub of the merchant/operator
    role: str  # always "merchant" for demo controls (spec s8, C2)
    reason: str  # enum-ish code, length-capped, never sent to an LLM (spec s8 item 4)
    at: datetime  # real UTC time of the jump


def sim_now(real_utc_now: datetime, offset_seconds: int) -> datetime:
    """Return the demo time: real UTC now plus the demo offset (spec s3: sim_now = real + offset).

    Inputs: real_utc_now (timezone-aware UTC), offset_seconds from demo_clock.
    Output: timezone-aware UTC datetime.
    Edge cases: offset 0 returns real time; rate is always real-time (no dilation, spec s3 I).
    """
    from datetime import timedelta

    return real_utc_now + timedelta(seconds=offset_seconds)


def validate_advance_delta(delta_seconds: int, max_advance_seconds: int) -> None:
    """Raise ValueError unless DEMO_MIN_ADVANCE_SECONDS <= delta_seconds <= max_advance_seconds.

    Inputs: delta_seconds from request body; max_advance_seconds from settings.
    Output: None on success; ValueError maps to HTTP 400 (api.md advance codes).
    Edge cases: delta 0 and negative values are rejected (forward-only clock, spec s3).
    """
    if delta_seconds < DEMO_MIN_ADVANCE_SECONDS:
        raise ValueError("delta_seconds must be forward-only (>= 1)")
    if delta_seconds > max_advance_seconds:
        raise ValueError(
            f"delta_seconds exceeds max_advance_seconds ({max_advance_seconds})"
        )


def apply_advance(snapshot: DemoClockSnapshot, delta_seconds: int) -> DemoClockSnapshot:
    """Return the snapshot after moving the offset forward by delta_seconds.

    Inputs: current snapshot (version = expected CAS value) and a validated positive delta.
    Output: new snapshot with offset += delta and version += 1.
    Edge cases: caller must still perform the CAS UPDATE ... WHERE version = :expected (spec s3);
    this function is the arithmetic only.
    """
    return DemoClockSnapshot(
        offset_seconds=snapshot.offset_seconds + delta_seconds,
        version=snapshot.version + 1,
    )
