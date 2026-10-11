"""Builds minimal valid event envelopes (api.md sec 1 request body) for tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any


def make_envelope(
    *,
    event_id: str | None = None,
    event_type: str = "ORDER_CAPTURED",
    producer: str = "checkout",
    actor_id: str = "buyer_77",
    order_id: str = "ord_123",
    amount: int = 5400,
) -> dict[str, Any]:
    event_id = event_id or str(uuid.uuid4())
    return {
        "event_id": event_id,
        "type": event_type,
        "version": 1,
        "occurred_at": datetime.now(UTC).isoformat(),
        "producer": producer,
        "aggregate_id": order_id,
        "trace_id": f"t_{event_id[:8]}",
        "request_id": f"r_{event_id[:8]}",
        "actor": {"type": "buyer", "id": actor_id, "auth_method": "session+csrf"},
        "refs": {"buyer_id": actor_id, "order_id": order_id},
        "payload": {"order_id": order_id, "total": amount, "currency": "USD"},
    }
