"""T25: banned phrases must never appear in render.v1 output."""

from __future__ import annotations

from app.mandate_logic import BANNED_PHRASES, render_text


def _sample_normalized() -> dict:
    return {
        "currency": "USD",
        "max_total_minor": 6000,
        "max_qty_per_line": 2,
        "merchant_allowlist": [{"merchant_id": "shop-a", "display_name": "Shop A"}],
        "intent_text": "birthday gift for a runner",
        "expires_at": "2026-11-01T12:00:00Z",
        "protection": {"kinds_covered": ["LATE", "LOST"], "max_refund_minor": 5000, "deliver_by_days": 7},
        "revoke_effect": "FUTURE_ONLY",
        "policy_version": "policy.v1",
    }


def test_render_text_has_no_banned_phrases():
    text = render_text(_sample_normalized())
    for phrase in BANNED_PHRASES:
        assert phrase.lower() not in text.lower(), f"banned phrase present: {phrase}"


def test_render_text_is_pure_and_deterministic():
    normalized = _sample_normalized()
    assert render_text(normalized) == render_text(normalized)


def test_render_text_includes_money_and_merchant():
    text = render_text(_sample_normalized())
    assert "USD 60.00" in text
    assert "Shop A (shop-a)" in text
    assert '"birthday gift for a runner"' in text
