from __future__ import annotations

from app.ratelimit import RateLimiter


def test_allows_up_to_limit_then_blocks():
    limiter = RateLimiter()
    for _ in range(5):
        allowed, _ = limiter.check("k", 5, 60.0)
        assert allowed is True
    allowed, retry_after = limiter.check("k", 5, 60.0)
    assert allowed is False
    assert retry_after > 0


def test_keys_are_independent():
    limiter = RateLimiter()
    for _ in range(5):
        limiter.check("a", 5, 60.0)
    allowed, _ = limiter.check("b", 5, 60.0)
    assert allowed is True
