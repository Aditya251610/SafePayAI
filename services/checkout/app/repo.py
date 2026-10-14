"""DB access layer for checkout: raw SQL via SQLAlchemy Core text(), no ORM models,
mirrors services/mandate/app/repo.py's pattern. Centralizes outbox inserts (ADR-003) and
the R4 "state written before external call" ordering so routers stay thin.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def now_utc() -> datetime:
    return datetime.now(UTC)


def to_jsonb_text(payload: Any) -> str:
    return json.dumps(payload, default=str)


async def insert_outbox_event(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_id: str,
    payload: dict,
    event_id: str | None = None,
) -> None:
    eid = event_id or str(uuid.uuid4())
    await session.execute(
        text(
            """
            INSERT INTO checkout.outbox (event_id, type, aggregate_id, payload)
            VALUES (:event_id, :type, :aggregate_id, :payload)
            ON CONFLICT (event_id) DO NOTHING
            """
        ),
        {
            "event_id": eid,
            "type": event_type,
            "aggregate_id": aggregate_id,
            "payload": to_jsonb_text(payload),
        },
    )


# ---------------------------------------------------------------------------
# Internal inbox/outbox/reconcile (api.md section 10)
# ---------------------------------------------------------------------------


async def inbox_event_is_new(
    session: AsyncSession, event_id: str, event_type: str
) -> bool:
    """INSERT ... ON CONFLICT DO NOTHING against the (event_id) PK -- True if this is the
    first time we've seen this event_id (at-least-once delivery, dedupe by event_id, same
    pattern as resolution's inbox_dedupe)."""
    result = await session.execute(
        text(
            """
            INSERT INTO checkout.inbox (event_id, type)
            VALUES (:event_id, :type)
            ON CONFLICT (event_id) DO NOTHING
            """
        ),
        {"event_id": event_id, "type": event_type},
    )
    return bool(result.rowcount)  # type: ignore[attr-defined]


async def block_carts_for_mandate(session: AsyncSession, mandate_id: str) -> int:
    """mandate.revoked (api.md s10): block un-captured carts under this mandate so a
    buyer can't confirm one into an order anymore. Carts that already became an order are
    untouched here -- that order's own capture-time live mandate check (orders.py's
    _mandate_status, spec s7 step 4) already catches the revocation organically, no
    separate flag needed."""
    result = await session.execute(
        text(
            """
            UPDATE checkout.carts SET status = 'BLOCKED'
            WHERE mandate_id = :mandate_id AND status IN ('CHECKED', 'NEEDS_CONFIRMATION')
            """
        ),
        {"mandate_id": mandate_id},
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


async def get_outbox_after(
    session: AsyncSession, *, after: int, limit: int = 100
) -> list[dict[str, Any]]:
    """GET /internal/outbox?after=seq (api.md s10: pull catch-up, ADR-003). Column list
    matches the real post-0002_outbox_align_schema shape (migrations/versions/
    0002_outbox_align_schema.py), not the baseline migration's original (pre-alignment)
    columns -- delivered_at doesn't exist; delivered_to/next_attempt_at/version/trace_id do."""
    result = await session.execute(
        text(
            "SELECT seq, event_id, type, version, aggregate_id, payload, attempts, "
            "trace_id, created_at, delivered_to, next_attempt_at "
            "FROM checkout.outbox WHERE seq > :after ORDER BY seq ASC LIMIT :limit"
        ),
        {"after": after, "limit": limit},
    )
    return [dict(row) for row in result.mappings().all()]


async def get_non_terminal_orders(
    session: AsyncSession, limit: int = 50
) -> list[dict[str, Any]]:
    """POST /internal/reconcile (api.md s10): orders stuck mid-flow (CAPTURABLE_STATES --
    AWAITING_APPROVAL/APPROVED/CAPTURE_UNKNOWN) that a buyer's own return/capture call
    never finished for, oldest first."""
    result = await session.execute(
        text(
            """
            SELECT order_id, mandate_id, status, version, created_at
            FROM checkout.orders
            WHERE status IN ('AWAITING_APPROVAL', 'APPROVED', 'CAPTURE_UNKNOWN')
            ORDER BY created_at ASC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    )
    return [dict(row) for row in result.mappings().all()]


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


async def idempotency_lookup(
    session: AsyncSession, principal: str, route: str, key: str
) -> dict | None:
    result = await session.execute(
        text(
            "SELECT request_hash, response_code, response_body FROM checkout.idempotency_keys "
            "WHERE principal = :principal AND route = :route AND key = :key"
        ),
        {"principal": principal, "route": route, "key": key},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def idempotency_store(
    session: AsyncSession,
    principal: str,
    route: str,
    key: str,
    request_hash: str,
    response_code: int,
    response_body: dict,
) -> None:
    await session.execute(
        text(
            "INSERT INTO checkout.idempotency_keys "
            "(principal, route, key, request_hash, response_code, response_body) "
            "VALUES (:principal, :route, :key, :request_hash, :response_code, :response_body)"
        ),
        {
            "principal": principal,
            "route": route,
            "key": key,
            "request_hash": request_hash,
            "response_code": response_code,
            "response_body": to_jsonb_text(response_body),
        },
    )


def request_hash_of(payload: dict) -> str:
    import hashlib

    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Carts
# ---------------------------------------------------------------------------

CART_COLUMNS = """
    cart_id, buyer_id, mandate_id, mandate_hash, status, lines, total_minor, currency,
    merchant_ids, catalog_version, proposal_hash, intent_fit_verdict,
    intent_fit_reason_code, intent_fit_confidence, stated_price_mismatch,
    committed_minor_at_check, created_at
"""


async def insert_cart(session: AsyncSession, **fields: Any) -> None:
    columns = [
        "cart_id",
        "buyer_id",
        "mandate_id",
        "mandate_hash",
        "status",
        "lines",
        "total_minor",
        "currency",
        "merchant_ids",
        "catalog_version",
        "proposal_hash",
        "stated_price_mismatch",
        "committed_minor_at_check",
    ]
    params = dict(fields)
    params["lines"] = to_jsonb_text(fields["lines"])
    params["merchant_ids"] = to_jsonb_text(fields["merchant_ids"])
    placeholders = ", ".join(f":{c}" for c in columns)
    await session.execute(
        text(
            f"INSERT INTO checkout.carts ({', '.join(columns)}) VALUES ({placeholders})"
        ),
        {k: params[k] for k in columns},
    )


async def get_cart_row(session: AsyncSession, cart_id: str) -> dict | None:
    result = await session.execute(
        text(f"SELECT {CART_COLUMNS} FROM checkout.carts WHERE cart_id = :id"),
        {"id": cart_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def insert_cart_check(
    session: AsyncSession,
    *,
    cart_id: str,
    phase: str,
    name: str,
    result: str,
    reason_code: str | None,
    detail: str | None,
    source: str,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO checkout.cart_checks (id, cart_id, phase, name, result, reason_code, detail, source)
            VALUES (:id, :cart_id, :phase, :name, :result, :reason_code, :detail, :source)
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "cart_id": cart_id,
            "phase": phase,
            "name": name,
            "result": result,
            "reason_code": reason_code,
            "detail": detail,
            "source": source,
        },
    )


async def sum_committed_minor(session: AsyncSession, mandate_id: str) -> int:
    """spec.md section 4 step 6: cumulative cap across orders in flight/complete."""
    result = await session.execute(
        text(
            """
            SELECT COALESCE(SUM(total_minor), 0) FROM checkout.orders
            WHERE mandate_id = :mandate_id
              AND status IN ('AWAITING_APPROVAL', 'APPROVED', 'CAPTURING',
                              'CAPTURE_PENDING', 'CAPTURE_UNKNOWN', 'CAPTURED')
            """
        ),
        {"mandate_id": mandate_id},
    )
    return int(result.scalar() or 0)


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

ORDER_COLUMNS = """
    order_id, cart_id, buyer_id, mandate_id, status, total_minor, currency,
    paypal_order_id, create_request_id, capture_request_id, custom_id, invoice_id,
    approve_url, last_paypal_status, failure_code, version, created_at, updated_at
"""


async def insert_order(session: AsyncSession, **fields: Any) -> None:
    columns = [
        "order_id",
        "cart_id",
        "buyer_id",
        "mandate_id",
        "status",
        "total_minor",
        "currency",
        "create_request_id",
        "custom_id",
        "invoice_id",
    ]
    await session.execute(
        text(
            f"INSERT INTO checkout.orders ({', '.join(columns)}) VALUES "
            f"({', '.join(f':{c}' for c in columns)})"
        ),
        {k: fields[k] for k in columns},
    )


async def get_order_row(session: AsyncSession, order_id: str) -> dict | None:
    result = await session.execute(
        text(f"SELECT {ORDER_COLUMNS} FROM checkout.orders WHERE order_id = :id"),
        {"id": order_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def get_order_by_cart(session: AsyncSession, cart_id: str) -> dict | None:
    result = await session.execute(
        text(f"SELECT {ORDER_COLUMNS} FROM checkout.orders WHERE cart_id = :id"),
        {"id": cart_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def cas_order_status(
    session: AsyncSession,
    order_id: str,
    expected_version: int,
    new_status: str,
    **fields: Any,
) -> bool:
    """Compare-and-swap on `orders.version`, per spec.md section 3. Returns False if
    another writer already moved the row (stale version)."""
    assignments = ["status = :status", "version = version + 1", "updated_at = now()"]
    params: dict[str, Any] = {
        "status": new_status,
        "order_id": order_id,
        "expected_version": expected_version,
    }
    for key, value in fields.items():
        assignments.append(f"{key} = :{key}")
        params[key] = value
    result = await session.execute(
        text(
            f"UPDATE checkout.orders SET {', '.join(assignments)} "
            "WHERE order_id = :order_id AND version = :expected_version"
        ),
        params,
    )
    return int(result.rowcount) == 1  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Return bindings
# ---------------------------------------------------------------------------


async def insert_return_binding(
    session: AsyncSession,
    *,
    state_hash: str,
    order_id: str,
    buyer_id: str,
    mandate_id: str,
    kind: str,
    exp: datetime,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO checkout.return_bindings (state_hash, order_id, buyer_id, mandate_id, kind, exp)
            VALUES (:state_hash, :order_id, :buyer_id, :mandate_id, :kind, :exp)
            """
        ),
        {
            "state_hash": state_hash,
            "order_id": order_id,
            "buyer_id": buyer_id,
            "mandate_id": mandate_id,
            "kind": kind,
            "exp": exp,
        },
    )


async def get_return_binding(session: AsyncSession, state_hash: str) -> dict | None:
    result = await session.execute(
        text(
            "SELECT state_hash, order_id, buyer_id, mandate_id, paypal_order_id, kind, exp, used_at "
            "FROM checkout.return_bindings WHERE state_hash = :state_hash"
        ),
        {"state_hash": state_hash},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def mark_return_binding_used(session: AsyncSession, state_hash: str) -> bool:
    result = await session.execute(
        text(
            "UPDATE checkout.return_bindings SET used_at = now() "
            "WHERE state_hash = :state_hash AND used_at IS NULL"
        ),
        {"state_hash": state_hash},
    )
    return int(result.rowcount) == 1  # type: ignore[attr-defined]


async def clear_return_binding_used(session: AsyncSession, state_hash: str) -> None:
    """spec.md section 7 step 6: NOT_APPROVED must leave the state usable for a retry --
    clear `used_at` in the same transaction that detected the order is not yet approved."""
    await session.execute(
        text(
            "UPDATE checkout.return_bindings SET used_at = NULL WHERE state_hash = :state_hash"
        ),
        {"state_hash": state_hash},
    )


async def set_return_binding_paypal_order_id(
    session: AsyncSession, order_id: str, paypal_order_id: str
) -> None:
    await session.execute(
        text(
            "UPDATE checkout.return_bindings SET paypal_order_id = :paypal_order_id "
            "WHERE order_id = :order_id"
        ),
        {"order_id": order_id, "paypal_order_id": paypal_order_id},
    )


# ---------------------------------------------------------------------------
# Captures / receipts
# ---------------------------------------------------------------------------


async def insert_capture(
    session: AsyncSession,
    *,
    capture_id: str,
    order_id: str,
    amount_minor: int,
    currency: str,
    paypal_status: str | None,
    custom_id: str | None,
    invoice_id: str | None,
    captured_at: datetime,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO checkout.captures
                (capture_id, order_id, amount_minor, currency, paypal_status,
                 custom_id, invoice_id, captured_at)
            VALUES
                (:capture_id, :order_id, :amount_minor, :currency, :paypal_status,
                 :custom_id, :invoice_id, :captured_at)
            ON CONFLICT (order_id) DO NOTHING
            """
        ),
        {
            "capture_id": capture_id,
            "order_id": order_id,
            "amount_minor": amount_minor,
            "currency": currency,
            "paypal_status": paypal_status,
            "custom_id": custom_id,
            "invoice_id": invoice_id,
            "captured_at": captured_at,
        },
    )


async def get_capture_row(session: AsyncSession, order_id: str) -> dict | None:
    result = await session.execute(
        text(
            "SELECT capture_id, order_id, amount_minor, currency, paypal_status, "
            "custom_id, invoice_id, captured_at FROM checkout.captures "
            "WHERE order_id = :order_id"
        ),
        {"order_id": order_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def insert_receipt(
    session: AsyncSession,
    *,
    order_id: str,
    receipt_json: dict,
    mandate_hash: str | None,
    audit_event_id: str | None,
    protection_window_days: int | None,
    remaining_cap_minor: int | None,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO checkout.receipts
                (order_id, receipt_json, mandate_hash, audit_event_id,
                 protection_window_days, remaining_cap_minor)
            VALUES
                (:order_id, :receipt_json, :mandate_hash, :audit_event_id,
                 :protection_window_days, :remaining_cap_minor)
            ON CONFLICT (order_id) DO NOTHING
            """
        ),
        {
            "order_id": order_id,
            "receipt_json": to_jsonb_text(receipt_json),
            "mandate_hash": mandate_hash,
            "audit_event_id": audit_event_id,
            "protection_window_days": protection_window_days,
            "remaining_cap_minor": remaining_cap_minor,
        },
    )


async def get_receipt_row(session: AsyncSession, order_id: str) -> dict | None:
    result = await session.execute(
        text(
            "SELECT order_id, receipt_json, mandate_hash, audit_event_id, "
            "protection_window_days, remaining_cap_minor, created_at "
            "FROM checkout.receipts WHERE order_id = :order_id"
        ),
        {"order_id": order_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def get_cart_checks(session: AsyncSession, cart_id: str) -> list[dict]:
    result = await session.execute(
        text(
            "SELECT name, result, reason_code, detail, source FROM checkout.cart_checks "
            "WHERE cart_id = :cart_id ORDER BY ts"
        ),
        {"cart_id": cart_id},
    )
    return [dict(r) for r in result.mappings().all()]
