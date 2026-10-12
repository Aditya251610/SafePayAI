"""Generic outbox -> audit HTTP relay (ADR-003, sprint-plan S2-06).

Pure mechanics, no business logic (CLAUDE.md libs/common rule):
  1. Claim a batch of undelivered rows from a producer's own `<schema>.outbox` table with
     `FOR UPDATE SKIP LOCKED` inside a short transaction, bumping `attempts`/`next_attempt_at`
     so a crash or an overlapping flush call does not retry the same rows immediately. Commit
     (release locks) before any network call -- data-architecture.md section 7 / R4 ("no
     transaction held open across an HTTP call").
  2. POST the claimed rows to audit's `/internal/events/batch` (api.md sec 1), authenticated
     with a short-lived self-issued service JWT (auth-gateway.md sec 3.1: "each service
     self-issues for service-originated calls"). The event's own `event_id` is both the
     envelope's idempotency key AND the dedupe key audit enforces server-side (confirmed in
     app/chain/append.py: a repeat `event_id` with identical content is a no-op `DUPLICATE`,
     not a duplicate row) -- so an HTTP retry here is always safe.
  3. On success, mark delivered rows' `delivered_to->'audit'` and clear `next_attempt_at` in a
     second short transaction. On failure (audit down, timeout, non-2xx, REJECTED item), do
     nothing further -- the claim step already bumped `attempts`/`next_attempt_at`, so the row
     is retried on a later flush. Events are never lost: audit being unreachable leaves rows
     pending, not dropped.

Every outbox table this module targets must share the canonical column shape documented in
data-architecture.md section 7: `seq, event_id, type, version, aggregate_id, payload, trace_id,
created_at, delivered_to (jsonb), attempts, next_attempt_at`. (checkout's table was missing
several of these columns until migration 0002_outbox_align_schema -- see that migration's
docstring.)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from safepayai_common.auth.jwt import ServiceJWTConfig, mint_service_token
from safepayai_common.http.client import DEFAULT_TIMEOUT

# ---------------------------------------------------------------------------
# Dev-only signing key (NOT a secret -- mirrors services/audit's own
# app/auth_fixtures/local_jwks.json fixture pattern). Every producer service
# defaults its outbox-relay signing key to this PEM so docker-compose/CI work
# out of the box; a real deployment overrides PS_<SLUG>_AUDIT_JWT_PRIVATE_KEY
# with its own key and updates audit's PS_AUDIT_TRUSTED_ISSUERS to match.
# ---------------------------------------------------------------------------
DEV_AUDIT_RELAY_KID = "ps-outbox-relay-dev"

DEV_AUDIT_RELAY_PRIVATE_KEY_PEM = """-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDOaQGfRObwZ9Je
BR/aH+Lk5ZLg3A1UrNg3wG0P/fWIFu+4oXYaWFG42mG5j3pgTzFbbcBN232HUZ1W
bB8oNG0gD+7D8P8WBJaMAGPq7dTYvz6CXKLUHEcxzI+AcrPL4TS1Wmxxzsn6GcOj
NfORKZQs8jpqPsdW4B+4LcUPVWACHgJR7kB1E+z5JPxDkX2+m3iam+IJcNEYZoIq
o/7p2QcVE/ZcrpYxqqEZyf3c3l59ZoiS5K1IuZE4leV5t7J9aULgdHwAhFi7EFoD
j73AjjuUy43/aL9xDYDW7SHRPGDrIdzCBnwWSUplymWzH+KGw8vQZqP34H+vyCbE
HLkjHdarAgMBAAECggEAKLkq6sNrVM8HACm+qQhVeZeZrOd9cdFQL1+1pMwUHy93
SFQCuxvls7TSRwv5tvqo4EL9B99gGsyNYDmgxAvj48mA8AOiMDPjh+ejzvvxXHoO
2SVxsquJmFelkFARDQ53mbgnYSTNUJy4roC8d01ewKdhwwhzx74cQ/gzwtyzPndW
ZxgDsz74aBuSU03PoCchyawME3DYolTh76b4moqEVGYkdB9+pD9FbEq7lZApfxle
JaXJCxa/vw0+4mg9bHfw7QiUBI7hWqNS5Ez/3A5az2FHzZcSyQEKTQvMu5UHge1g
4xyKERFtXiMGJoCmrlsVe19O0VYCMyPUuHsKrxrYoQKBgQDx4XDJV3b3vP3R5EjN
IdqwQdpFEblIUIyU5vbJkEi3aHQUmnm2E/OUsRdZC1H/JHdsf1nwDfliK8phYWEc
8v/Swb6JooHyVfY0FbLwoKNrVTOsr+X0mHYesL9Q8D4VJtcONj1qri79CbA5c7bc
R0VsN6hbX+6tsLtMnw2lO3zjaQKBgQDadYLBdJimDrwVmwjM2KZK9stmGF3sREb5
VMPQTku15dWFIk+/S2mkKBIyIyob921SqWGpnHt3CvQvKiKOUeD0ywK+6DpGNiAt
JLUpIQ+zlbd+0EQFufxVAD4EDTBx4WsuhYAvRWzQwQeEPlNDAsFWKdBqZbfbtvEi
616bU5Tq8wKBgQCD6TuWQmH6F5KhDgt5+7WFHFTKCDFws6UHa7I5GLvfclKkDd7E
orrbY3zlLdxI9f0/KXDGDwjrNhCH7RCGNiu4J7se2oZdv+2mWBMfUavt1Ch7S+5v
51m7wQ6FOI/S/zyXXpM+A8JScx8tJeMa3K+Kpgvl0TqcdN6gmblaXEfuyQKBgQCd
ce3AAYl2vM3fgHHyOP54rq/fMBaZDohccDQEMDmuqiueHSF+jBpiHiMnEWLq7wNS
fRMPC+GL5VAhoetvySEpLBsZfgNp0N6VyovqTZKkanXqJq2vtuBeXqNThjHxEXaO
+9Zru0x2k3gYXlbhx92RfOdhl1fQOWRHN31i0vVT8wKBgAHryNQ/h//GEHEC6YOI
39XBfGix+DN2sNeDq8XAwhXWzOoI+Lk0a509i9UkO8x1D6K8mBlwtqMeSJ+n4GEV
20tU/BhoH5FPPeNm5hvSawdP7cdEXjXIS6JgOyj5ncuZqZne+DpOtdwoIZWA9bEn
5XtHzVssolWzmZ08snVZ+K0i
-----END PRIVATE KEY-----
"""

DEV_AUDIT_RELAY_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAzmkBn0Tm8GfSXgUf2h/i
5OWS4NwNVKzYN8BtD/31iBbvuKF2GlhRuNphuY96YE8xW23ATdt9h1GdVmwfKDRt
IA/uw/D/FgSWjABj6u3U2L8+glyi1BxHMcyPgHKzy+E0tVpscc7J+hnDozXzkSmU
LPI6aj7HVuAfuC3FD1VgAh4CUe5AdRPs+ST8Q5F9vpt4mpviCXDRGGaCKqP+6dkH
FRP2XK6WMaqhGcn93N5efWaIkuStSLmROJXlebeyfWlC4HR8AIRYuxBaA4+9wI47
lMuN/2i/cQ2A1u0h0Txg6yHcwgZ8FklKZcplsx/ihsPL0Gaj9+B/r8gmxBy5Ix3W
qwIDAQAB
-----END PUBLIC KEY-----
"""


@dataclass(frozen=True)
class OutboxRelayConfig:
    """Everything the relay needs to flush one producer's outbox to audit."""

    schema: str
    """Producer's own Postgres schema, e.g. "mandate", "checkout"."""

    producer: str
    """Service slug used as the audit envelope's `producer` field and the minted JWT `sub`
    (must equal audit's PS_AUDIT_* producer allow-list entry for this service)."""

    audit_base_url: str
    jwt: ServiceJWTConfig
    batch_size: int = 100
    retry_backoff_seconds: int = 30
    """Base backoff; actual delay is `retry_backoff_seconds * attempts` after a claim."""
    request_timeout: httpx.Timeout = field(default_factory=lambda: DEFAULT_TIMEOUT)


@dataclass(frozen=True)
class RelayResult:
    delivered: int
    failed: int
    pending: int


def _row_to_envelope(row: Any, *, producer: str) -> dict[str, Any]:
    occurred_at = row["created_at"] or datetime.now(UTC)
    trace_id = row["trace_id"] or str(uuid.uuid4())
    return {
        "event_id": str(row["event_id"]),
        "type": row["type"],
        "version": row["version"] if row["version"] is not None else 1,
        "occurred_at": occurred_at.isoformat(),
        "producer": producer,
        "aggregate_id": str(row["aggregate_id"]) if row["aggregate_id"] is not None else None,
        "trace_id": str(trace_id),
        "request_id": str(uuid.uuid4()),
        "actor": {"type": "system", "id": producer, "auth_method": "service_jwt"},
        "payload": row["payload"],
    }


async def _claim_batch(session: AsyncSession, config: OutboxRelayConfig) -> list[Any]:
    async with session.begin():
        result = await session.execute(
            text(
                f"""
                SELECT seq, event_id, type, version, aggregate_id, payload, trace_id, created_at
                FROM "{config.schema}".outbox
                WHERE (delivered_to -> 'audit') IS NULL
                  AND (next_attempt_at IS NULL OR next_attempt_at <= now())
                ORDER BY seq ASC
                LIMIT :limit
                FOR UPDATE SKIP LOCKED
                """
            ),
            {"limit": config.batch_size},
        )
        claimed = result.mappings().all()
        if claimed:
            seqs = [row["seq"] for row in claimed]
            await session.execute(
                text(
                    f"""
                    UPDATE "{config.schema}".outbox
                    SET attempts = attempts + 1,
                        next_attempt_at = now() + make_interval(secs => :backoff * (attempts + 1))
                    WHERE seq = ANY(:seqs)
                    """
                ),
                {"seqs": seqs, "backoff": config.retry_backoff_seconds},
            )
    return list(claimed)


async def _mark_delivered(
    session: AsyncSession, config: OutboxRelayConfig, seqs: list[int]
) -> None:
    if not seqs:
        return
    async with session.begin():
        await session.execute(
            text(
                f"""
                UPDATE "{config.schema}".outbox
                SET delivered_to = delivered_to || '{{"audit": true}}'::jsonb,
                    next_attempt_at = NULL
                WHERE seq = ANY(:seqs)
                """
            ),
            {"seqs": seqs},
        )


async def _count_pending(session: AsyncSession, config: OutboxRelayConfig) -> int:
    result = await session.execute(
        text(
            f"""SELECT count(*) FROM "{config.schema}".outbox
            WHERE (delivered_to -> 'audit') IS NULL"""
        )
    )
    return int(result.scalar() or 0)


async def flush_outbox(
    session: AsyncSession,
    config: OutboxRelayConfig,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> RelayResult:
    """Run one relay pass for `config.schema`'s outbox table. Safe to call repeatedly
    (idempotent per-row via the claim step) and safe under concurrent callers (SKIP LOCKED)."""
    claimed = await _claim_batch(session, config)
    if not claimed:
        pending = await _count_pending(session, config)
        return RelayResult(delivered=0, failed=0, pending=pending)

    envelopes = [_row_to_envelope(row, producer=config.producer) for row in claimed]
    seq_by_event_id = {str(row["event_id"]): row["seq"] for row in claimed}

    token = mint_service_token(config.producer, config.jwt)
    headers = {"Authorization": f"Bearer {token}"}

    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(
        base_url=config.audit_base_url, timeout=config.request_timeout
    )

    delivered_seqs: list[int] = []
    failed = 0
    try:
        try:
            response = await client.post(
                "/internal/events/batch",
                json={"events": envelopes},
                headers=headers,
            )
        except httpx.HTTPError:
            # Audit unreachable: every claimed row stays pending (attempts/next_attempt_at
            # were already bumped by the claim step) -- events are retained, not lost.
            failed = len(claimed)
        else:
            if response.status_code == 200:
                for item in response.json().get("results", []):
                    seq = seq_by_event_id.get(item.get("event_id"))
                    if seq is None:
                        continue
                    if item.get("status") in ("APPENDED", "DUPLICATE"):
                        delivered_seqs.append(seq)
                    else:
                        failed += 1
            else:
                failed = len(claimed)
    finally:
        if owns_client:
            await client.aclose()

    await _mark_delivered(session, config, delivered_seqs)
    pending = await _count_pending(session, config)
    return RelayResult(delivered=len(delivered_seqs), failed=failed, pending=pending)
