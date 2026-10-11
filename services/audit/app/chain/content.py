"""Builds the content object that gets canonicalized and hashed (spec.md sec 4).

Exact keys: `v, chain_id, event_id, event_type, event_version, producer, occurred_at,
recorded_at, actor{type,id,auth_method,session_id_hash?}, request_id, trace_id,
refs{buyer_id?,mandate_id?,order_id?,case_id?}, payload`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

CONTENT_VERSION = 1


def format_ts(dt: datetime) -> str:
    """UTC, `YYYY-MM-DDTHH:MM:SS.ffffffZ`, exactly 6 fractional digits (spec.md sec 4)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    dt = dt.astimezone(UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def build_content(
    *,
    chain_id: str,
    event_id: str,
    event_type: str,
    event_version: int,
    producer: str,
    occurred_at: datetime,
    recorded_at: datetime,
    actor: dict[str, Any],
    request_id: str,
    trace_id: str,
    refs: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    actor_obj: dict[str, Any] = {
        "type": actor["type"],
        "id": actor["id"],
        "auth_method": actor["auth_method"],
    }
    if actor.get("session_id_hash"):
        actor_obj["session_id_hash"] = actor["session_id_hash"]

    refs_obj = {k: v for k, v in refs.items() if v is not None}

    return {
        "v": CONTENT_VERSION,
        "chain_id": chain_id,
        "event_id": event_id,
        "event_type": event_type,
        "event_version": event_version,
        "producer": producer,
        "occurred_at": format_ts(occurred_at),
        "recorded_at": format_ts(recorded_at),
        "actor": actor_obj,
        "request_id": request_id,
        "trace_id": trace_id,
        "refs": refs_obj,
        "payload": payload,
    }
