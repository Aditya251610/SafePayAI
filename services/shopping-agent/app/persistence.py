"""Writes to the `agent` schema: `proposal_log` (spec.md section 12) and the
`outbox` row for `cart.proposed` (ADR-003 -- every state-changing write that crosses a
service boundary goes through an outbox row in the SAME transaction as the write it
describes; no direct cross-service DB access).

Raw buyer intent text is never stored -- only `input_sha256`/`output_sha256` and the
validated, escaped output (spec.md section 12: "Raw intent text not stored, hash only").
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def write_proposal_log(
    session: AsyncSession,
    *,
    trace_id: uuid.UUID,
    mandate_id: uuid.UUID,
    kind: str,
    prompt_version: str,
    provider: str | None,
    model: str | None,
    source: str,
    input_sha256: str,
    output_sha256: str | None,
    output_json: dict[str, Any] | None,
    validation_result: str | None,
    injection_suspected: bool,
    latency_ms: int | None,
    attempts: int,
) -> uuid.UUID:
    proposal_id = uuid.uuid4()
    await session.execute(
        text(
            """
            INSERT INTO agent.proposal_log
                (id, trace_id, mandate_id, kind, prompt_version, provider, model, source,
                 input_sha256, output_sha256, output_json, validation_result,
                 injection_suspected, latency_ms, attempts)
            VALUES
                (:id, :trace_id, :mandate_id, :kind, :prompt_version, :provider, :model,
                 :source, :input_sha256, :output_sha256,
                 CAST(:output_json AS JSONB), :validation_result, :injection_suspected,
                 :latency_ms, :attempts)
            """
        ),
        {
            "id": proposal_id,
            "trace_id": trace_id,
            "mandate_id": mandate_id,
            "kind": kind,
            "prompt_version": prompt_version,
            "provider": provider,
            "model": model,
            "source": source,
            "input_sha256": input_sha256,
            "output_sha256": output_sha256,
            "output_json": json.dumps(output_json) if output_json is not None else None,
            "validation_result": validation_result,
            "injection_suspected": injection_suspected,
            "latency_ms": latency_ms,
            "attempts": attempts,
        },
    )
    return proposal_id


async def write_cart_proposed_outbox(
    session: AsyncSession,
    *,
    proposal_id: uuid.UUID,
    mandate_id: uuid.UUID,
    trace_id: uuid.UUID,
    prompt_version: str,
    provider: str | None,
    model: str | None,
    source: str,
    input_sha256: str,
    output_sha256: str | None,
    validation_result: str | None,
    injection_suspected: bool,
    latency_ms: int | None,
) -> None:
    """api.md section 8: emitted after every /propose call whose status != NO_PROPOSAL."""
    payload = {
        "proposal_id": str(proposal_id),
        "mandate_id": str(mandate_id),
        "kind": "cart",
        "prompt_version": prompt_version,
        "provider": provider,
        "model": model,
        "source": source,
        "input_sha256": input_sha256,
        "output_sha256": output_sha256,
        "validation_result": validation_result,
        "injection_suspected": injection_suspected,
        "latency_ms": latency_ms,
        "trace_id": str(trace_id),
    }
    await session.execute(
        text(
            """
            INSERT INTO agent.outbox (event_id, type, version, aggregate_id, payload, trace_id)
            VALUES (:event_id, :type, 1, :aggregate_id, CAST(:payload AS JSONB), :trace_id)
            """
        ),
        {
            "event_id": uuid.uuid4(),
            "type": "cart.proposed",
            "aggregate_id": proposal_id,
            "payload": json.dumps(payload),
            "trace_id": trace_id,
        },
    )


async def get_outbox_after(
    session: AsyncSession, *, after: int, limit: int = 100
) -> list[dict[str, Any]]:
    """GET /internal/outbox?after=seq (api.md section 7: pull catch-up, ADR-003)."""
    result = await session.execute(
        text(
            """
            SELECT seq, event_id, type, version, aggregate_id, payload, attempts,
                   trace_id, created_at, delivered_to, next_attempt_at, done
            FROM agent.outbox WHERE seq > :after ORDER BY seq ASC LIMIT :limit
            """
        ),
        {"after": after, "limit": limit},
    )
    return [dict(row) for row in result.mappings().all()]


async def read_proposal_log(
    session: AsyncSession, proposal_id: uuid.UUID
) -> dict[str, Any] | None:
    result = await session.execute(
        text(
            """
            SELECT id, trace_id, mandate_id, source, output_json, validation_result,
                   provider, model, latency_ms
            FROM agent.proposal_log
            WHERE id = :id
            """
        ),
        {"id": proposal_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None


__all__ = [
    "read_proposal_log",
    "sha256_hex",
    "write_cart_proposed_outbox",
    "write_proposal_log",
]
