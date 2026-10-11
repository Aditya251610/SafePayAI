"""In-process rate limiter (spec.md section 6.3 / REQ-GW-023).

Fixed-window counter keyed by an arbitrary string (caller builds the key, e.g.
"auth:<ip>" or "auth-login:<ip>:<handle>"). Single instance, in-memory: resets on
restart (R7, acknowledged in spec.md). No new infra dependency added - deployment.md
does not provision Redis for Wave 5, and the task brief says not to add one without
checking it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class _Window:
    window_start: float
    count: int = 0


class RateLimiter:
    def __init__(self) -> None:
        self._windows: dict[str, _Window] = {}

    def check(self, key: str, limit: int, window_s: float) -> tuple[bool, float]:
        """Returns (allowed, retry_after_s). Fixed window, resets every window_s."""
        now = time.monotonic()
        win = self._windows.get(key)
        if win is None or now - win.window_start >= window_s:
            win = _Window(window_start=now, count=0)
            self._windows[key] = win

        win.count += 1
        if win.count > limit:
            retry_after = max(0.0, window_s - (now - win.window_start))
            return False, retry_after
        return True, 0.0

    def reset(self) -> None:
        """Test helper - clears all state."""
        self._windows.clear()


# Module-level singleton; one process, one limiter (spec.md R7).
limiter = RateLimiter()
