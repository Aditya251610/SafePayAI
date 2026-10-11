"""call_ledger access: idempotency per spec.md section 6. Raw SQL via SQLAlchemy Core
text(), no ORM -- matches mandate/app/repo.py's convention for this repo.

Conflict handling on insert (spec.md section 6):
  - existing DONE and same body_sha256 -> served from ledger, `replayed=true`, no PayPal call.
  - existing (any state) and different body_sha256 -> IDEMPOTENCY_KEY_REUSED (REJECTED).
  - existing IN_FLIGHT, same body -> IN_PROGRESS (local concurrent duplicate), no PayPal call.
  - existing UNKNOWN -> return UNKNOWN again.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


def body_sha256(body: dict[str, Any]) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LedgerRow:
    request_id: str
    op: str
    caller: str
    body_sha256: str
    state: str
    paypal_http_status: int | None
    paypal_object_id: str | None
    response_json_redacted: dict[str, Any] | None


async def get_ledger_row(session: AsyncSession, request_id: str) -> LedgerRow | None:
    result = await session.execute(
        text(
            "SELECT request_id, op, caller, body_sha256, state, paypal_http_status, "
            "paypal_object_id, response_json_redacted FROM paypal.call_ledger "
            "WHERE request_id = :request_id"
        ),
        {"request_id": request_id},
    )
    row = result.mappings().first()
    if row is None:
        return None
    return LedgerRow(
        request_id=str(row["request_id"]),
        op=row["op"],
        caller=row["caller"],
        body_sha256=row["body_sha256"],
        state=row["state"],
        paypal_http_status=row["paypal_http_status"],
        paypal_object_id=row["paypal_object_id"],
        response_json_redacted=row["response_json_redacted"],
    )


async def insert_in_flight(
    session: AsyncSession,
    *,
    request_id: str,
    op: str,
    caller: str,
    body_hash: str,
) -> bool:
    """Returns True if this call won the insert race (row created, caller must proceed
    to call PayPal). Returns False if a row already existed (caller must inspect it via
    get_ledger_row and decide replay / IN_PROGRESS / IDEMPOTENCY_KEY_REUSED)."""
    try:
        await session.execute(
            text(
                "INSERT INTO paypal.call_ledger (request_id, op, caller, body_sha256, state) "
                "VALUES (:request_id, :op, :caller, :body_hash, 'IN_FLIGHT')"
            ),
            {"request_id": request_id, "op": op, "caller": caller, "body_hash": body_hash},
        )
        await session.commit()
        return True
    except IntegrityError:
        await session.rollback()
        return False


async def mark_done(
    session: AsyncSession,
    request_id: str,
    *,
    state: str,
    paypal_http_status: int | None,
    paypal_object_id: str | None,
    response_json_redacted: dict[str, Any] | None,
) -> None:
    await session.execute(
        text(
            "UPDATE paypal.call_ledger SET state = :state, paypal_http_status = :http_status, "
            "paypal_object_id = :object_id, response_json_redacted = :response, updated = now() "
            "WHERE request_id = :request_id"
        ),
        {
            "state": state,
            "http_status": paypal_http_status,
            "object_id": paypal_object_id,
            "response": json.dumps(response_json_redacted) if response_json_redacted else None,
            "request_id": request_id,
        },
    )
    await session.commit()


async def insert_outbox_event(
    session: AsyncSession,
    *,
    event_id: str,
    event_type: str,
    aggregate_id: str | None,
    payload: dict[str, Any],
    trace_id: str | None,
) -> None:
    """ADR-003: every state-changing write that crosses a service boundary goes through
    an outbox row. Written in the same transaction as the ledger DONE update by the
    caller (ops.py commits once after both)."""
    await session.execute(
        text(
            "INSERT INTO paypal.outbox (event_id, type, aggregate_id, payload, trace_id) "
            "VALUES (:event_id, :type, :aggregate_id, :payload, :trace_id) "
            "ON CONFLICT (event_id) DO NOTHING"
        ),
        {
            "event_id": event_id,
            "type": event_type,
            "aggregate_id": aggregate_id,
            "payload": json.dumps(payload),
            "trace_id": trace_id,
        },
    )
    await session.commit()
