"""Shared outbox-relay mechanics (ADR-003). No business logic -- see relay.py docstring."""

from __future__ import annotations

from safepayai_common.outbox.relay import (
    DEV_AUDIT_RELAY_KID,
    DEV_AUDIT_RELAY_PRIVATE_KEY_PEM,
    DEV_AUDIT_RELAY_PUBLIC_KEY_PEM,
    OutboxRelayConfig,
    RelayResult,
    flush_outbox,
)

__all__ = [
    "DEV_AUDIT_RELAY_KID",
    "DEV_AUDIT_RELAY_PRIVATE_KEY_PEM",
    "DEV_AUDIT_RELAY_PUBLIC_KEY_PEM",
    "OutboxRelayConfig",
    "RelayResult",
    "flush_outbox",
]
