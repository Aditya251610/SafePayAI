"""DB access layer for resolution: raw SQL via SQLAlchemy Core text(), no ORM writes at
runtime. Mirrors services/checkout/app/repo.py's pattern (ADR-003 outbox). `app/models.py`
documents the ORM shape for reference; migrations are hand-written and authoritative.
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
# Outbox
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
            INSERT INTO resolution.outbox (event_id, type, aggregate_id, payload, trace_id)
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
# Control flags (kill switch, spec s9)
# ---------------------------------------------------------------------------


async def get_control_flags(session: AsyncSession) -> dict[str, Any] | None:
    result = await session.execute(
        text(
            "SELECT id, refunds_frozen, reason, set_by, epoch FROM resolution.control_flags WHERE id = 1"
        )
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def set_refunds_frozen(
    session: AsyncSession, *, frozen: bool, reason: str, set_by: str
) -> int:
    result = await session.execute(
        text(
            """
            UPDATE resolution.control_flags
            SET refunds_frozen = :frozen, reason = :reason, set_by = :set_by, set_at = now(), epoch = epoch + 1
            WHERE id = 1
            RETURNING epoch
            """
        ),
        {"frozen": frozen, "reason": reason, "set_by": set_by},
    )
    return int(result.scalar() or 0)


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------

CASE_COLUMNS = (
    "id, order_id, capture_id, mandate_id, buyer_id, kind, origin, state, version, "
    "terms_snapshot, terms_hash, opened_at, window_hold, amount_minor, currency, triage, "
    "untrusted_text, human_review_reason, human_review_entered_at, created_at"
)


async def get_case_by_order_and_kind(
    session: AsyncSession, order_id: str, kind: str
) -> dict[str, Any] | None:
    result = await session.execute(
        text(
            f"SELECT {CASE_COLUMNS} FROM resolution.cases WHERE order_id = :order_id AND kind = :kind"
        ),
        {"order_id": order_id, "kind": kind},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def get_case(session: AsyncSession, case_id: uuid.UUID) -> dict[str, Any] | None:
    result = await session.execute(
        text(f"SELECT {CASE_COLUMNS} FROM resolution.cases WHERE id = :id"),
        {"id": case_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def get_case_for_update(
    session: AsyncSession, case_id: uuid.UUID
) -> dict[str, Any] | None:
    result = await session.execute(
        text(f"SELECT {CASE_COLUMNS} FROM resolution.cases WHERE id = :id FOR UPDATE"),
        {"id": case_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def list_cases(
    session: AsyncSession,
    *,
    status: str | None = None,
    order_id: str | None = None,
    buyer_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """GET /cases (api.md section 3.3-adjacent list route). buyer_id scopes a buyer's own
    view (api.md section 1 ownership rule); status/order_id are optional filters."""
    conditions = []
    params: dict[str, Any] = {"limit": limit}
    if status:
        conditions.append("state = :status")
        params["status"] = status
    if order_id:
        conditions.append("order_id = :order_id")
        params["order_id"] = order_id
    if buyer_id:
        conditions.append("buyer_id = :buyer_id")
        params["buyer_id"] = buyer_id
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    result = await session.execute(
        text(
            f"SELECT {CASE_COLUMNS} FROM resolution.cases {where_clause} "
            "ORDER BY opened_at DESC LIMIT :limit"
        ),
        params,
    )
    return [dict(row) for row in result.mappings().all()]


async def get_review_queue(session: AsyncSession) -> list[dict[str, Any]]:
    """GET /review/queue (api.md section 3.3): HUMAN_REVIEW cases, oldest first."""
    result = await session.execute(
        text(
            f"SELECT {CASE_COLUMNS} FROM resolution.cases "
            "WHERE state = 'HUMAN_REVIEW' ORDER BY human_review_entered_at ASC NULLS LAST, "
            "opened_at ASC"
        )
    )
    return [dict(row) for row in result.mappings().all()]


async def insert_case(
    session: AsyncSession,
    *,
    case_id: uuid.UUID,
    order_id: str,
    capture_id: str | None,
    mandate_id: str | None,
    buyer_id: str | None,
    kind: str,
    origin: str,
    state: str,
    terms_snapshot: dict[str, Any] | None,
    terms_hash: str | None,
    opened_at: datetime,
    window_hold: bool,
    untrusted_text: str | None,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO resolution.cases
                (id, order_id, capture_id, mandate_id, buyer_id, kind, origin, state, version,
                 terms_snapshot, terms_hash, opened_at, window_hold, untrusted_text)
            VALUES
                (:id, :order_id, :capture_id, :mandate_id, :buyer_id, :kind, :origin, :state, 0,
                 :terms_snapshot, :terms_hash, :opened_at, :window_hold, :untrusted_text)
            ON CONFLICT (order_id, kind) DO NOTHING
            """
        ),
        {
            "id": case_id,
            "order_id": order_id,
            "capture_id": capture_id,
            "mandate_id": mandate_id,
            "buyer_id": buyer_id,
            "kind": kind,
            "origin": origin,
            "state": state,
            "terms_snapshot": to_jsonb_text(terms_snapshot)
            if terms_snapshot is not None
            else None,
            "terms_hash": terms_hash,
            "opened_at": opened_at,
            "window_hold": window_hold,
            "untrusted_text": untrusted_text,
        },
    )


async def cas_case_state(
    session: AsyncSession,
    *,
    case_id: uuid.UUID,
    expected_state: str,
    expected_version: int,
    new_state: str,
    **extra_fields: Any,
) -> bool:
    assignments = ["state = :new_state", "version = version + 1"]
    params: dict[str, Any] = {
        "id": case_id,
        "expected_state": expected_state,
        "expected_version": expected_version,
        "new_state": new_state,
    }
    for key, value in extra_fields.items():
        assignments.append(f"{key} = :{key}")
        params[key] = value
    result = await session.execute(
        text(
            f"UPDATE resolution.cases SET {', '.join(assignments)} "
            "WHERE id = :id AND state = :expected_state AND version = :expected_version"
        ),
        params,
    )
    return int(result.rowcount) == 1  # type: ignore[attr-defined]


async def insert_case_transition(
    session: AsyncSession,
    *,
    case_id: uuid.UUID,
    from_state: str | None,
    to_state: str,
    actor: str,
    reason: str | None,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO resolution.case_transitions (id, case_id, from_state, to_state, actor, reason)
            VALUES (:id, :case_id, :from_state, :to_state, :actor, :reason)
            """
        ),
        {
            "id": uuid.uuid4(),
            "case_id": case_id,
            "from_state": from_state,
            "to_state": to_state,
            "actor": actor,
            "reason": reason,
        },
    )


# ---------------------------------------------------------------------------
# Offers
# ---------------------------------------------------------------------------

OFFER_COLUMNS = (
    "id, case_id, offer_seq, action, amount_minor, currency, tier, status, proposal_hash, "
    "expires_at, created_at"
)


async def get_next_offer_seq(session: AsyncSession, case_id: uuid.UUID) -> int:
    result = await session.execute(
        text(
            "SELECT COALESCE(MAX(offer_seq), 0) + 1 FROM resolution.offers WHERE case_id = :case_id"
        ),
        {"case_id": case_id},
    )
    return int(result.scalar() or 1)


async def insert_offer(
    session: AsyncSession,
    *,
    offer_id: uuid.UUID,
    case_id: uuid.UUID,
    offer_seq: int,
    action: str,
    amount_minor: int,
    currency: str,
    tier: str,
    proposal_hash: str,
    expires_at: datetime | None,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO resolution.offers
                (id, case_id, offer_seq, action, amount_minor, currency, tier, status, proposal_hash, expires_at)
            VALUES
                (:id, :case_id, :offer_seq, :action, :amount_minor, :currency, :tier, 'ACTIVE', :proposal_hash, :expires_at)
            """
        ),
        {
            "id": offer_id,
            "case_id": case_id,
            "offer_seq": offer_seq,
            "action": action,
            "amount_minor": amount_minor,
            "currency": currency,
            "tier": tier,
            "proposal_hash": proposal_hash,
            "expires_at": expires_at,
        },
    )


async def get_offer(
    session: AsyncSession, offer_id: uuid.UUID
) -> dict[str, Any] | None:
    result = await session.execute(
        text(f"SELECT {OFFER_COLUMNS} FROM resolution.offers WHERE id = :id"),
        {"id": offer_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def cas_accept_offer(session: AsyncSession, offer_id: uuid.UUID) -> bool:
    """Single winner: UPDATE offers SET status='ACCEPTED' WHERE status='ACTIVE' (spec s13)."""
    result = await session.execute(
        text(
            "UPDATE resolution.offers SET status = 'ACCEPTED' WHERE id = :id AND status = 'ACTIVE'"
        ),
        {"id": offer_id},
    )
    return int(result.rowcount) == 1  # type: ignore[attr-defined]


async def cas_decline_offer(session: AsyncSession, offer_id: uuid.UUID) -> bool:
    result = await session.execute(
        text(
            "UPDATE resolution.offers SET status = 'SUPERSEDED' WHERE id = :id AND status = 'ACTIVE'"
        ),
        {"id": offer_id},
    )
    return int(result.rowcount) == 1  # type: ignore[attr-defined]


async def supersede_active_offers(
    session: AsyncSession, case_id: uuid.UUID, superseded_by: uuid.UUID
) -> None:
    await session.execute(
        text(
            "UPDATE resolution.offers SET status = 'SUPERSEDED' "
            "WHERE case_id = :case_id AND status = 'ACTIVE' AND id != :superseded_by"
        ),
        {"case_id": case_id, "superseded_by": superseded_by},
    )


# ---------------------------------------------------------------------------
# Policy decisions
# ---------------------------------------------------------------------------


async def insert_policy_decision(
    session: AsyncSession,
    *,
    case_id: uuid.UUID,
    klass: str,
    policy_version: str,
    reasons: list[str],
    facts_hash: str,
    checks: list[dict[str, Any]] | None = None,
) -> uuid.UUID:
    decision_id = uuid.uuid4()
    await session.execute(
        text(
            """
            INSERT INTO resolution.policy_decisions (id, case_id, klass, policy_version, reasons, facts_hash, checks)
            VALUES (:id, :case_id, :klass, :policy_version, :reasons, :facts_hash, :checks)
            """
        ),
        {
            "id": decision_id,
            "case_id": case_id,
            "klass": klass,
            "policy_version": policy_version,
            "reasons": to_jsonb_text(reasons),
            "facts_hash": facts_hash,
            "checks": to_jsonb_text(checks) if checks is not None else None,
        },
    )
    return decision_id


# ---------------------------------------------------------------------------
# Refund attempts
# ---------------------------------------------------------------------------

ATTEMPT_COLUMNS = (
    "id, case_id, order_id, request_id, invoice_id, amount_minor, status, paypal_refund_id, "
    "reconcile_count, sent_at, created_at"
)


async def get_attempt_for_case(
    session: AsyncSession, case_id: uuid.UUID
) -> dict[str, Any] | None:
    result = await session.execute(
        text(
            f"SELECT {ATTEMPT_COLUMNS} FROM resolution.refund_attempts WHERE case_id = :case_id"
        ),
        {"case_id": case_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def get_live_attempt_for_order(
    session: AsyncSession, order_id: str
) -> dict[str, Any] | None:
    result = await session.execute(
        text(
            f"SELECT {ATTEMPT_COLUMNS} FROM resolution.refund_attempts "
            "WHERE order_id = :order_id AND status IN ('REQUESTED','SENT','UNKNOWN','COMPLETED')"
        ),
        {"order_id": order_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def insert_refund_attempt(
    session: AsyncSession,
    *,
    attempt_id: uuid.UUID,
    case_id: uuid.UUID,
    order_id: str,
    request_id: uuid.UUID,
    invoice_id: str,
    capture_id: str,
    amount_minor: int,
    currency: str,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO resolution.refund_attempts
                (id, case_id, order_id, request_id, invoice_id, capture_id, amount_minor, currency, status)
            VALUES
                (:id, :case_id, :order_id, :request_id, :invoice_id, :capture_id, :amount_minor, :currency, 'REQUESTED')
            """
        ),
        {
            "id": attempt_id,
            "case_id": case_id,
            "order_id": order_id,
            "request_id": str(request_id),
            "invoice_id": invoice_id,
            "capture_id": capture_id,
            "amount_minor": amount_minor,
            "currency": currency,
        },
    )


async def update_attempt_status(
    session: AsyncSession,
    *,
    attempt_id: uuid.UUID,
    new_status: str,
    paypal_refund_id: str | None = None,
    sent_at: datetime | None = None,
    bump_reconcile: bool = False,
) -> None:
    assignments = ["status = :new_status"]
    params: dict[str, Any] = {"id": attempt_id, "new_status": new_status}
    if paypal_refund_id is not None:
        assignments.append("paypal_refund_id = :paypal_refund_id")
        params["paypal_refund_id"] = paypal_refund_id
    if sent_at is not None:
        assignments.append("sent_at = :sent_at")
        params["sent_at"] = sent_at
    if bump_reconcile:
        assignments.append("reconcile_count = reconcile_count + 1")
    await session.execute(
        text(
            f"UPDATE resolution.refund_attempts SET {', '.join(assignments)} WHERE id = :id"
        ),
        params,
    )


async def get_latest_policy_decision(
    session: AsyncSession, case_id: uuid.UUID
) -> dict[str, Any] | None:
    result = await session.execute(
        text(
            "SELECT id, case_id, klass, policy_version, reasons, facts_hash, checks, created_at "
            "FROM resolution.policy_decisions WHERE case_id = :case_id ORDER BY created_at DESC LIMIT 1"
        ),
        {"case_id": case_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def get_latest_offer_for_case(
    session: AsyncSession, case_id: uuid.UUID
) -> dict[str, Any] | None:
    result = await session.execute(
        text(
            f"SELECT {OFFER_COLUMNS} FROM resolution.offers WHERE case_id = :case_id ORDER BY offer_seq DESC LIMIT 1"
        ),
        {"case_id": case_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def update_policy_decision_checks(
    session: AsyncSession, decision_id: uuid.UUID, checks: list[dict[str, Any]]
) -> None:
    await session.execute(
        text("UPDATE resolution.policy_decisions SET checks = :checks WHERE id = :id"),
        {"id": decision_id, "checks": to_jsonb_text(checks)},
    )


async def get_reconcilable_attempts(
    session: AsyncSession, *, min_age_seconds: int, limit: int
) -> list[dict[str, Any]]:
    result = await session.execute(
        text(
            f"""
            SELECT {ATTEMPT_COLUMNS} FROM resolution.refund_attempts
            WHERE status IN ('SENT', 'UNKNOWN')
              AND sent_at IS NOT NULL
              AND sent_at < now() - make_interval(secs => :min_age_seconds)
            ORDER BY sent_at ASC
            LIMIT :limit
            FOR UPDATE SKIP LOCKED
            """
        ),
        {"min_age_seconds": min_age_seconds, "limit": limit},
    )
    return [dict(row) for row in result.mappings().all()]


async def count_buyer_completed_refunds_in_window(
    session: AsyncSession, buyer_id: str, window_start: datetime
) -> int:
    result = await session.execute(
        text(
            """
            SELECT COUNT(*) FROM resolution.refund_attempts ra
            JOIN resolution.cases c ON c.id = ra.case_id
            WHERE c.buyer_id = :buyer_id AND ra.status = 'COMPLETED' AND ra.created_at >= :window_start
            """
        ),
        {"buyer_id": buyer_id, "window_start": window_start},
    )
    return int(result.scalar() or 0)
