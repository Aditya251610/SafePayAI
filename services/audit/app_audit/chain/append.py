"""Append algorithm -- spec.md sec 3 option B (advisory lock, chosen).

1. Validate producer == verified token sub (caller does this before calling in).
2. BEGIN; SELECT pg_advisory_xact_lock(key).
3. Duplicate check on event_id (idempotency key) -- duplicates are a no-op; a duplicate
   event_id with DIFFERENT content is EventIdConflict (api.md sec 1 `409
   EVENT_ID_CONFLICT`, "a producer bug; never overwritten").
4. SELECT seq, row_hash FROM entries ORDER BY seq DESC LIMIT 1 (the head). Empty is a
   configuration error (genesis missing).
5. For each new event in order: seq = head.seq+1, prev_hash = head.row_hash,
   row_hash = SHA256(DOMAIN || prev_hash || canonical); INSERT; advance head.
6. The BEFORE INSERT linkage trigger (migration 0001) re-checks the same invariant
   independently -- this is the defense-in-depth half of the design, not duplicated here.
7. COMMIT (caller's responsibility, via `session.begin()`).

ADVISORY_LOCK_KEY must match migrations/versions/0001_baseline.py's constant exactly --
the lock is re-entrant only because both sides use the identical 63-bit key.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Text, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app_audit.chain.canonical import CanonicalizationError, canonicalize
from app_audit.chain.content import build_content
from app_audit.chain.hashing import row_hash as compute_row_hash
from app_audit.schemas.events import EventEnvelope

ADVISORY_LOCK_KEY = 727274726269743139


class ProducerMismatch(Exception):
    """envelope.producer != verified token sub (api.md sec 1 403 PRODUCER_MISMATCH)."""

    def __init__(self, event_id: str) -> None:
        self.event_id = event_id
        super().__init__(f"producer mismatch for event_id={event_id}")


class EventIdConflict(Exception):
    """Same event_id, different content (api.md sec 1 409 EVENT_ID_CONFLICT)."""

    def __init__(self, event_id: str, seq: int, row_hash: str) -> None:
        self.event_id = event_id
        self.seq = seq
        self.row_hash = row_hash
        super().__init__(f"event_id {event_id} already recorded with different content")


class ChainConfigurationError(Exception):
    """Genesis row missing -- refuse rather than silently start a new chain."""


@dataclass
class AppendOutcome:
    event_id: str
    status: str  # "APPENDED" | "DUPLICATE"
    seq: int
    row_hash: str


def _content_fingerprint(envelope: EventEnvelope) -> tuple[Any, ...]:
    """The business-content fields that must match for a duplicate event_id to be a
    legitimate retry rather than a producer bug (spec.md sec 4 step 1: recorded_at is
    stamped fresh per attempt and is deliberately excluded here)."""
    return (
        envelope.type,
        envelope.version,
        envelope.producer,
        envelope.actor.type,
        envelope.actor.id,
        envelope.actor.auth_method,
        envelope.payload,
    )


async def append_batch(
    session: AsyncSession,
    *,
    chain_id: str,
    producer_sub: str,
    envelopes: list[EventEnvelope],
) -> list[AppendOutcome]:
    if not envelopes:
        return []

    for env in envelopes:
        if env.producer != producer_sub:
            raise ProducerMismatch(env.event_id)

    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": ADVISORY_LOCK_KEY})

    event_ids = [env.event_id for env in envelopes]
    dup_query = text(
        "SELECT event_id, seq, row_hash, event_type, event_version, producer,"
        " actor_type, actor_id, auth_method, payload"
        " FROM entries WHERE event_id::text = ANY(:ids)"
    ).bindparams(bindparam("ids", type_=ARRAY(Text())))
    dup_rows = (await session.execute(dup_query, {"ids": event_ids})).mappings().all()
    dup_by_id = {str(r["event_id"]): r for r in dup_rows}

    head_row = (
        await session.execute(text("SELECT seq, row_hash FROM entries ORDER BY seq DESC LIMIT 1"))
    ).first()
    if head_row is None:
        raise ChainConfigurationError("genesis row missing")
    head_seq, head_hash = head_row

    outcomes: list[AppendOutcome] = []
    insert_stmt = text(
        "INSERT INTO entries (seq, chain_id, event_id, event_type, event_version, producer,"
        " occurred_at, recorded_at, actor_type, actor_id, auth_method, request_id, trace_id,"
        " buyer_id, mandate_id, order_id, case_id, canonical, payload, prev_hash, row_hash)"
        " VALUES (:seq, :chain_id, :event_id, :event_type, :event_version, :producer,"
        " :occurred_at, :recorded_at, :actor_type, :actor_id, :auth_method, :request_id, :trace_id,"
        " :buyer_id, :mandate_id, :order_id, :case_id, :canonical, :payload, :prev_hash, :row_hash)"
    ).bindparams(bindparam("payload", type_=JSONB))

    for env in envelopes:
        existing = dup_by_id.get(env.event_id)
        if existing is not None:
            existing_payload = existing["payload"]
            fingerprint = (
                existing["event_type"],
                existing["event_version"],
                existing["producer"],
                existing["actor_type"],
                existing["actor_id"],
                existing["auth_method"],
                existing_payload,
            )
            if fingerprint != _content_fingerprint(env):
                raise EventIdConflict(env.event_id, existing["seq"], existing["row_hash"])
            outcomes.append(
                AppendOutcome(env.event_id, "DUPLICATE", existing["seq"], existing["row_hash"])
            )
            continue

        recorded_at = datetime.now(UTC)
        refs = env.refs.model_dump()
        actor = env.actor.model_dump()
        content = build_content(
            chain_id=chain_id,
            event_id=env.event_id,
            event_type=env.type,
            event_version=env.version,
            producer=env.producer,
            occurred_at=env.occurred_at,
            recorded_at=recorded_at,
            actor=actor,
            request_id=env.request_id,
            trace_id=env.trace_id,
            refs=refs,
            payload=env.payload,
        )
        try:
            canonical_bytes = canonicalize(content)
        except CanonicalizationError as exc:
            raise ValueError(f"CANONICALIZATION_FAILED:{exc}") from exc

        new_seq = head_seq + 1
        new_hash = compute_row_hash(head_hash, canonical_bytes)

        await session.execute(
            insert_stmt,
            {
                "seq": new_seq,
                "chain_id": chain_id,
                "event_id": env.event_id,
                "event_type": env.type,
                "event_version": env.version,
                "producer": env.producer,
                "occurred_at": env.occurred_at,
                "recorded_at": recorded_at,
                "actor_type": env.actor.type,
                "actor_id": env.actor.id,
                "auth_method": env.actor.auth_method,
                "request_id": env.request_id,
                "trace_id": env.trace_id,
                "buyer_id": refs.get("buyer_id"),
                "mandate_id": refs.get("mandate_id"),
                "order_id": refs.get("order_id"),
                "case_id": refs.get("case_id"),
                "canonical": canonical_bytes.decode("utf-8"),
                "payload": env.payload,
                "prev_hash": head_hash,
                "row_hash": new_hash,
            },
        )
        outcomes.append(AppendOutcome(env.event_id, "APPENDED", new_seq, new_hash))
        head_seq, head_hash = new_seq, new_hash

    return outcomes


async def append_one(
    session: AsyncSession, *, chain_id: str, producer_sub: str, envelope: EventEnvelope
) -> AppendOutcome:
    results = await append_batch(
        session, chain_id=chain_id, producer_sub=producer_sub, envelopes=[envelope]
    )
    return results[0]
