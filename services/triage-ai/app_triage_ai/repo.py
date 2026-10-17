"""DB access layer for triage-ai: `triage_log` + `outbox` inserts (ADR-003 - outbox write
always happens in the SAME transaction as the state change) and the idempotency lookup by
`(case_id, task, input_sha256, prompt_version)` (spec.md section 10: same inputs replay the
stored result instead of re-calling the LLM, cutting quota burn and giving pure replay
semantics)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def find_existing(
    session: AsyncSession,
    *,
    case_id: str,
    task: str,
    input_sha256: str,
    prompt_version: str,
) -> dict[str, Any] | None:
    result = await session.execute(
        text(
            """
            SELECT triage_id, category, confidence, route, reasons, flags, gate_hits,
                   status, model, source, latency_ms, created_at
            FROM triage.triage_log
            WHERE case_id = :case_id AND task = :task AND input_sha256 = :input_sha256
              AND prompt_version = :prompt_version
            ORDER BY created_at DESC
            LIMIT 1
            """
        ),
        {
            "case_id": case_id,
            "task": task,
            "input_sha256": input_sha256,
            "prompt_version": prompt_version,
        },
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def insert_triage_log(session: AsyncSession, fields: dict[str, Any]) -> None:
    await session.execute(
        text(
            """
            INSERT INTO triage.triage_log
                (triage_id, case_id, trace_id, task, prompt_version, model, source,
                 input_sha256, output_sha256, category, confidence, route, reasons,
                 flags, gate_hits, tokens_in, tokens_out, latency_ms, status, truncated)
            VALUES
                (:triage_id, :case_id, :trace_id, :task, :prompt_version, :model, :source,
                 :input_sha256, :output_sha256, :category, :confidence, :route, :reasons,
                 :flags, :gate_hits, :tokens_in, :tokens_out, :latency_ms, :status, :truncated)
            """
        ),
        fields,
    )


async def insert_outbox_event(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_id: str,
    payload: dict[str, Any],
    trace_id: str | None,
    event_id: str | None = None,
) -> None:
    """Writes `triage.outbox` in the caller's existing transaction (ADR-003). No raw buyer/
    carrier text ever belongs in `payload` - ids, task, category, confidence, route, reason
    codes, flag codes, hashes only (spec.md section 10)."""
    await session.execute(
        text(
            """
            INSERT INTO triage.outbox (event_id, type, version, aggregate_id, payload, trace_id)
            VALUES (:event_id, :type, 1, :aggregate_id, :payload, :trace_id)
            ON CONFLICT (event_id) DO NOTHING
            """
        ),
        {
            "event_id": event_id or str(uuid.uuid4()),
            "type": event_type,
            "aggregate_id": aggregate_id,
            "payload": json.dumps(payload),
            "trace_id": trace_id,
        },
    )


__all__ = ["find_existing", "insert_outbox_event", "insert_triage_log"]
