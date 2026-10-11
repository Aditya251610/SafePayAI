"""DB access layer for tracking: raw SQL via SQLAlchemy Core text(), no ORM writes at runtime.

Mirrors services/checkout/app/repo.py's pattern (ADR-003 outbox, R4 ordering). `app/models.py`
documents the DDL shape for reference; migrations are hand-written and authoritative.
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


# ---------------------------------------------------------------------------
# Outbox / inbox
# ---------------------------------------------------------------------------


async def insert_outbox_event(
    session: AsyncSession,
    *,
    event_id: uuid.UUID,
    event_type: str,
    aggregate_id: str,
    payload: dict[str, Any],
    trace_id: str | None = None,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO tracking.outbox (event_id, type, aggregate_id, payload, trace_id)
            VALUES (:event_id, :type, :aggregate_id, :payload, :trace_id)
            ON CONFLICT (event_id) DO NOTHING
            """
        ),
        {
            "event_id": event_id,
            "type": event_type,
            "aggregate_id": aggregate_id,
            "payload": to_jsonb_text(payload),
            "trace_id": trace_id,
        },
    )


# ---------------------------------------------------------------------------
# orders_seen
# ---------------------------------------------------------------------------


async def get_order_seen(session: AsyncSession, order_id: str) -> dict[str, Any] | None:
    result = await session.execute(
        text(
            "SELECT order_id, capture_id, mandate_id, protected_until_sim, seen_at "
            "FROM tracking.orders_seen WHERE order_id = :order_id"
        ),
        {"order_id": order_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def upsert_order_seen(
    session: AsyncSession,
    *,
    order_id: str,
    capture_id: str,
    mandate_id: str,
    protected_until_sim: datetime | None,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO tracking.orders_seen
                (order_id, capture_id, mandate_id, protected_until_sim, seen_at)
            VALUES (:order_id, :capture_id, :mandate_id, :protected_until_sim, now())
            ON CONFLICT (order_id) DO UPDATE SET
                capture_id = EXCLUDED.capture_id,
                mandate_id = EXCLUDED.mandate_id,
                protected_until_sim = EXCLUDED.protected_until_sim,
                seen_at = now()
            """
        ),
        {
            "order_id": order_id,
            "capture_id": capture_id,
            "mandate_id": mandate_id,
            "protected_until_sim": protected_until_sim,
        },
    )


# ---------------------------------------------------------------------------
# Shipments
# ---------------------------------------------------------------------------

SHIPMENT_COLUMNS = (
    "id, order_id, capture_id, mandate_id, tracking_number, carrier_name, status, anomaly, "
    "outcome_profile, promised_at_sim, created_at_sim, paypal_tracker_id, paypal_sync, "
    "paypal_last_error, active, demo, version"
)


async def get_shipment(
    session: AsyncSession, shipment_id: uuid.UUID
) -> dict[str, Any] | None:
    result = await session.execute(
        text(f"SELECT {SHIPMENT_COLUMNS} FROM tracking.shipments WHERE id = :id"),
        {"id": shipment_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def get_shipment_for_update(
    session: AsyncSession, shipment_id: uuid.UUID
) -> dict[str, Any] | None:
    result = await session.execute(
        text(
            f"SELECT {SHIPMENT_COLUMNS} FROM tracking.shipments WHERE id = :id FOR UPDATE"
        ),
        {"id": shipment_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def get_shipments_by_order(
    session: AsyncSession, order_id: str
) -> list[dict[str, Any]]:
    result = await session.execute(
        text(
            f"SELECT {SHIPMENT_COLUMNS} FROM tracking.shipments WHERE order_id = :order_id"
        ),
        {"order_id": order_id},
    )
    return [dict(row) for row in result.mappings().all()]


async def get_shipment_by_order_and_tracking(
    session: AsyncSession, order_id: str, tracking_number: str
) -> dict[str, Any] | None:
    result = await session.execute(
        text(
            f"SELECT {SHIPMENT_COLUMNS} FROM tracking.shipments "
            "WHERE order_id = :order_id AND tracking_number = :tracking_number"
        ),
        {"order_id": order_id, "tracking_number": tracking_number},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def get_active_nonterminal_shipments(
    session: AsyncSession,
) -> list[dict[str, Any]]:
    result = await session.execute(
        text(
            f"SELECT {SHIPMENT_COLUMNS} FROM tracking.shipments "
            "WHERE active = true AND status NOT IN ('DELIVERED', 'CANCELLED') "
            "FOR UPDATE SKIP LOCKED"
        )
    )
    return [dict(row) for row in result.mappings().all()]


async def insert_shipment(session: AsyncSession, **fields: Any) -> None:
    columns = [
        "id",
        "order_id",
        "capture_id",
        "mandate_id",
        "tracking_number",
        "carrier_name",
        "status",
        "outcome_profile",
        "promised_at_sim",
        "created_at_sim",
        "paypal_sync",
        "active",
        "demo",
        "version",
    ]
    placeholders = ", ".join(f":{c}" for c in columns)
    await session.execute(
        text(
            f"INSERT INTO tracking.shipments ({', '.join(columns)}) VALUES ({placeholders})"
        ),
        {k: fields[k] for k in columns},
    )


async def update_shipment_status_cas(
    session: AsyncSession,
    *,
    shipment_id: uuid.UUID,
    expected_version: int,
    new_status: str,
    anomaly: str | None,
    active: bool,
) -> bool:
    result = await session.execute(
        text(
            """
            UPDATE tracking.shipments
            SET status = :new_status, anomaly = :anomaly, active = :active, version = version + 1
            WHERE id = :id AND version = :expected_version
            """
        ),
        {
            "id": shipment_id,
            "new_status": new_status,
            "anomaly": anomaly,
            "active": active,
            "expected_version": expected_version,
        },
    )
    return int(result.rowcount) == 1  # type: ignore[attr-defined]


async def update_shipment_paypal_sync(
    session: AsyncSession,
    *,
    shipment_id: uuid.UUID,
    paypal_tracker_id: str | None,
    paypal_sync: str,
    paypal_last_error: str | None,
) -> None:
    await session.execute(
        text(
            """
            UPDATE tracking.shipments
            SET paypal_tracker_id = :paypal_tracker_id, paypal_sync = :paypal_sync,
                paypal_last_error = :paypal_last_error
            WHERE id = :id
            """
        ),
        {
            "id": shipment_id,
            "paypal_tracker_id": paypal_tracker_id,
            "paypal_sync": paypal_sync,
            "paypal_last_error": paypal_last_error,
        },
    )


# ---------------------------------------------------------------------------
# Scheduled events
# ---------------------------------------------------------------------------


async def insert_scheduled_event(
    session: AsyncSession,
    *,
    shipment_id: uuid.UUID,
    seq: int,
    due_at_sim: datetime,
    to_status: str,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO tracking.scheduled_events (shipment_id, seq, due_at_sim, to_status)
            VALUES (:shipment_id, :seq, :due_at_sim, :to_status)
            """
        ),
        {
            "shipment_id": shipment_id,
            "seq": seq,
            "due_at_sim": due_at_sim,
            "to_status": to_status,
        },
    )


async def get_due_scheduled_events(
    session: AsyncSession, shipment_id: uuid.UUID, sim_now: datetime
) -> list[dict[str, Any]]:
    result = await session.execute(
        text(
            """
            SELECT shipment_id, seq, due_at_sim, to_status, applied_at, applied_by
            FROM tracking.scheduled_events
            WHERE shipment_id = :shipment_id AND due_at_sim <= :sim_now AND applied_at IS NULL
            ORDER BY seq ASC
            """
        ),
        {"shipment_id": shipment_id, "sim_now": sim_now},
    )
    return [dict(row) for row in result.mappings().all()]


async def mark_scheduled_event_applied(
    session: AsyncSession,
    *,
    shipment_id: uuid.UUID,
    seq: int,
    applied_at: datetime,
    applied_by: str,
) -> bool:
    result = await session.execute(
        text(
            """
            UPDATE tracking.scheduled_events
            SET applied_at = :applied_at, applied_by = :applied_by
            WHERE shipment_id = :shipment_id AND seq = :seq AND applied_at IS NULL
            """
        ),
        {
            "shipment_id": shipment_id,
            "seq": seq,
            "applied_at": applied_at,
            "applied_by": applied_by,
        },
    )
    return int(result.rowcount) == 1  # type: ignore[attr-defined]


async def get_all_scheduled_events(
    session: AsyncSession, shipment_id: uuid.UUID
) -> list[dict[str, Any]]:
    result = await session.execute(
        text(
            "SELECT shipment_id, seq, due_at_sim, to_status, applied_at, applied_by "
            "FROM tracking.scheduled_events WHERE shipment_id = :shipment_id ORDER BY seq ASC"
        ),
        {"shipment_id": shipment_id},
    )
    return [dict(row) for row in result.mappings().all()]


# ---------------------------------------------------------------------------
# Shipment events (append-only history)
# ---------------------------------------------------------------------------


async def insert_shipment_event(
    session: AsyncSession,
    *,
    shipment_id: uuid.UUID,
    seq: int,
    from_status: str | None,
    to_status: str,
    source: str,
    occurred_at_sim: datetime,
    actor: str,
    note_code: str | None,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO tracking.shipment_events
                (id, shipment_id, seq, from_status, to_status, source, occurred_at_sim, actor, note_code)
            VALUES
                (:id, :shipment_id, :seq, :from_status, :to_status, :source,
                 :occurred_at_sim, :actor, :note_code)
            """
        ),
        {
            "id": uuid.uuid4(),
            "shipment_id": shipment_id,
            "seq": seq,
            "from_status": from_status,
            "to_status": to_status,
            "source": source,
            "occurred_at_sim": occurred_at_sim,
            "actor": actor,
            "note_code": note_code,
        },
    )


async def next_shipment_event_seq(session: AsyncSession, shipment_id: uuid.UUID) -> int:
    result = await session.execute(
        text(
            "SELECT COALESCE(MAX(seq), 0) + 1 FROM tracking.shipment_events "
            "WHERE shipment_id = :shipment_id"
        ),
        {"shipment_id": shipment_id},
    )
    return int(result.scalar() or 1)


async def get_last_event_sim(
    session: AsyncSession, shipment_id: uuid.UUID
) -> datetime | None:
    result = await session.execute(
        text(
            "SELECT occurred_at_sim FROM tracking.shipment_events "
            "WHERE shipment_id = :shipment_id ORDER BY seq DESC LIMIT 1"
        ),
        {"shipment_id": shipment_id},
    )
    return result.scalar()


async def get_delivered_at_sim(
    session: AsyncSession, shipment_id: uuid.UUID
) -> datetime | None:
    result = await session.execute(
        text(
            "SELECT occurred_at_sim FROM tracking.shipment_events "
            "WHERE shipment_id = :shipment_id AND to_status = 'DELIVERED' ORDER BY seq DESC LIMIT 1"
        ),
        {"shipment_id": shipment_id},
    )
    return result.scalar()


# ---------------------------------------------------------------------------
# Detections
# ---------------------------------------------------------------------------


async def insert_detection_if_absent(
    session: AsyncSession,
    *,
    shipment_id: uuid.UUID,
    kind: str,
    detected_at_sim: datetime,
    event_id: uuid.UUID,
) -> bool:
    """INSERT ... ON CONFLICT DO NOTHING RETURNING shipment_id (spec s4 item 2). True = inserted."""
    result = await session.execute(
        text(
            """
            INSERT INTO tracking.detections (shipment_id, kind, detected_at_sim, event_id, emitted)
            VALUES (:shipment_id, :kind, :detected_at_sim, :event_id, true)
            ON CONFLICT (shipment_id, kind) DO NOTHING
            RETURNING shipment_id
            """
        ),
        {
            "shipment_id": shipment_id,
            "kind": kind,
            "detected_at_sim": detected_at_sim,
            "event_id": event_id,
        },
    )
    return result.first() is not None


async def delete_detections_for_shipment(
    session: AsyncSession, shipment_id: uuid.UUID
) -> None:
    await session.execute(
        text("DELETE FROM tracking.detections WHERE shipment_id = :shipment_id"),
        {"shipment_id": shipment_id},
    )


# ---------------------------------------------------------------------------
# Demo clock / clock jumps
# ---------------------------------------------------------------------------


async def get_demo_clock(session: AsyncSession) -> dict[str, Any]:
    result = await session.execute(
        text(
            "SELECT id, offset_seconds, version FROM tracking.demo_clock "
            "WHERE id = 1 FOR UPDATE"
        )
    )
    row = result.mappings().first()
    if row is None:
        await session.execute(
            text(
                "INSERT INTO tracking.demo_clock (id, offset_seconds, version, updated_at) "
                "VALUES (1, 0, 0, now()) ON CONFLICT (id) DO NOTHING"
            )
        )
        result = await session.execute(
            text(
                "SELECT id, offset_seconds, version FROM tracking.demo_clock "
                "WHERE id = 1 FOR UPDATE"
            )
        )
        row = result.mappings().first()
    return dict(row) if row else {"id": 1, "offset_seconds": 0, "version": 0}


async def get_demo_clock_nolock(session: AsyncSession) -> dict[str, Any]:
    result = await session.execute(
        text("SELECT id, offset_seconds, version FROM tracking.demo_clock WHERE id = 1")
    )
    row = result.mappings().first()
    return dict(row) if row else {"id": 1, "offset_seconds": 0, "version": 0}


async def update_demo_clock_cas(
    session: AsyncSession, *, new_offset: int, expected_version: int
) -> bool:
    result = await session.execute(
        text(
            """
            UPDATE tracking.demo_clock
            SET offset_seconds = :new_offset, version = version + 1, updated_at = now()
            WHERE id = 1 AND version = :expected_version
            """
        ),
        {"new_offset": new_offset, "expected_version": expected_version},
    )
    return int(result.rowcount) == 1  # type: ignore[attr-defined]


async def reset_demo_clock(session: AsyncSession) -> None:
    await session.execute(
        text(
            "UPDATE tracking.demo_clock SET offset_seconds = 0, version = version + 1, "
            "updated_at = now() WHERE id = 1"
        )
    )


async def get_clock_jump_by_key(
    session: AsyncSession, idempotency_key: str
) -> dict[str, Any] | None:
    result = await session.execute(
        text(
            "SELECT id, idempotency_key, from_sim, to_sim, actor, reason, at "
            "FROM tracking.clock_jumps WHERE idempotency_key = :key"
        ),
        {"key": idempotency_key},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def insert_clock_jump(
    session: AsyncSession,
    *,
    idempotency_key: str,
    from_sim: datetime,
    to_sim: datetime,
    actor: str,
    reason: str,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO tracking.clock_jumps
                (id, idempotency_key, from_sim, to_sim, actor, reason, at)
            VALUES (:id, :idempotency_key, :from_sim, :to_sim, :actor, :reason, now())
            """
        ),
        {
            "id": uuid.uuid4(),
            "idempotency_key": idempotency_key,
            "from_sim": from_sim,
            "to_sim": to_sim,
            "actor": actor,
            "reason": reason,
        },
    )


async def get_demo_shipment_ids(session: AsyncSession) -> list[uuid.UUID]:
    result = await session.execute(
        text("SELECT id FROM tracking.shipments WHERE demo = true")
    )
    return [row[0] for row in result.all()]


# ---------------------------------------------------------------------------
# Tick lease / detector runs
# ---------------------------------------------------------------------------


async def try_acquire_lease(
    session: AsyncSession, *, name: str, holder: str, ttl_seconds: int
) -> bool:
    result = await session.execute(
        text(
            """
            INSERT INTO tracking.tick_lease (name, holder, expires_at)
            VALUES (:name, :holder, now() + make_interval(secs => :ttl_seconds))
            ON CONFLICT (name) DO UPDATE SET
                holder = EXCLUDED.holder,
                expires_at = EXCLUDED.expires_at
            WHERE tracking.tick_lease.expires_at < now()
            RETURNING name
            """
        ),
        {"name": name, "holder": holder, "ttl_seconds": ttl_seconds},
    )
    return result.first() is not None


async def insert_detector_run(
    session: AsyncSession, *, trigger: str, started_at: datetime, skipped_lease: bool
) -> uuid.UUID:
    run_id = uuid.uuid4()
    await session.execute(
        text(
            """
            INSERT INTO tracking.detector_runs (id, trigger, started_at, skipped_lease)
            VALUES (:id, :trigger, :started_at, :skipped_lease)
            """
        ),
        {
            "id": run_id,
            "trigger": trigger,
            "started_at": started_at,
            "skipped_lease": skipped_lease,
        },
    )
    return run_id


async def finish_detector_run(
    session: AsyncSession, *, run_id: uuid.UUID, applied_count: int, detected_count: int
) -> None:
    await session.execute(
        text(
            """
            UPDATE tracking.detector_runs
            SET finished_at = now(), applied_count = :applied_count,
                detected_count = :detected_count
            WHERE id = :id
            """
        ),
        {
            "id": run_id,
            "applied_count": applied_count,
            "detected_count": detected_count,
        },
    )
