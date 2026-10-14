"""Internal/cron endpoints - mandate/spec.md sections 5 & 7.4, api.md section 12.

Guarded by INTERNAL_TICK_SECRET (shared bare name, conventions doc section 2).
Never routed by the gateway (404 externally).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from safepayai_common.auth.jwt import ServiceJWTConfig
from safepayai_common.outbox import OutboxRelayConfig, flush_outbox
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import repo
from app.deps import get_session
from app.settings import Settings, get_bare_secrets, get_settings

router = APIRouter(prefix="/internal", tags=["internal"])


def _relay_config(settings: Settings) -> OutboxRelayConfig:
    """S2-06: one OutboxRelayConfig per service, built from its own settings -- the relay
    mechanics themselves live in libs/common/safepayai_common/outbox/relay.py (shared)."""
    return OutboxRelayConfig(
        schema="mandate",
        producer="mandate",
        audit_base_url=settings.outbox_relay_audit_base_url,
        jwt=ServiceJWTConfig(
            issuer=settings.outbox_relay_jwt_issuer,
            audience="audit",
            signing_key_pem=settings.outbox_relay_jwt_private_key,
            kid=settings.outbox_relay_jwt_kid,
        ),
        batch_size=settings.outbox_relay_batch_size,
    )


def _require_tick_secret(x_tick_secret: str | None) -> None:
    secrets = get_bare_secrets()
    if (
        not secrets.internal_tick_secret
        or x_tick_secret != secrets.internal_tick_secret
    ):
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")


@router.post("/sweep")
async def sweep(
    response: Response,
    x_tick_secret: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _require_tick_secret(x_tick_secret)
    settings = get_settings()

    expired_emitted = 0
    reservations_released = 0
    stuck_capture_alerts = 0

    async with session.begin():
        # Emit mandate.expired (once, deterministic id) for mandates past expiry
        # that have not yet had any spend reservation sweep touch them this tick.
        expired_rows = await session.execute(
            text(
                "SELECT mandate_id, mandate_hash, expires_at FROM mandate.mandates "
                "WHERE expires_at <= now() AND mandate_id NOT IN "
                "(SELECT mandate_id FROM mandate.revocations)"
            )
        )
        for row in expired_rows.mappings().all():
            event_id = repo.deterministic_event_id(
                str(row["mandate_id"]), "mandate.expired"
            )
            await repo.insert_outbox_event(
                session,
                event_type="mandate.expired",
                mandate_id=str(row["mandate_id"]),
                event_id=event_id,
                payload={
                    "mandate_id": str(row["mandate_id"]),
                    "mandate_hash": row["mandate_hash"],
                    "expired_at": row["expires_at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            )
            expired_emitted += 1

        # Release stale RESERVED reservations whose TTL has passed.
        stale = await session.execute(
            text(
                "SELECT reservation_id, mandate_id, amount_minor FROM mandate.spend_reservations "
                "WHERE state = 'RESERVED' AND expires_at IS NOT NULL AND expires_at <= now()"
            )
        )
        for row in stale.mappings().all():
            await repo.set_reservation_state(
                session,
                str(row["reservation_id"]),
                "RELEASED",
                release_reason="TTL_EXPIRED",
            )
            await repo.adjust_spend(
                session, str(row["mandate_id"]), reserved_delta=-row["amount_minor"]
            )
            reservations_released += 1

        stuck = await session.execute(
            text(
                "SELECT count(*) FROM mandate.spend_reservations WHERE state IN ('CAPTURING','CAPTURE_UNKNOWN') "
                "AND updated_at <= now() - make_interval(secs => :secs)"
            ),
            {"secs": settings.stuck_capture_alert_seconds},
        )
        stuck_capture_alerts = stuck.scalar() or 0

    return {
        "expired_emitted": expired_emitted,
        "reservations_released": reservations_released,
        "stuck_capture_alerts": stuck_capture_alerts,
    }


@router.get("/outbox")
async def outbox_pull(
    response: Response,
    after: int = 0,
    x_tick_secret: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _require_tick_secret(x_tick_secret)
    async with session.begin():
        result = await session.execute(
            text(
                "SELECT seq, event_id, type, version, aggregate_id, payload, trace_id, created_at "
                "FROM mandate.outbox WHERE seq > :after ORDER BY seq ASC LIMIT 500"
            ),
            {"after": after},
        )
        rows = result.mappings().all()
        events = [
            {
                "seq": r["seq"],
                "event_id": str(r["event_id"]),
                "type": r["type"],
                "version": r["version"],
                "aggregate_id": r["aggregate_id"],
                "payload": r["payload"],
                "trace_id": r["trace_id"],
                "created_at": r["created_at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            for r in rows
        ]
    return {"events": events}


@router.post("/outbox/flush")
async def outbox_flush(
    response: Response,
    x_tick_secret: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """S2-06: actual HTTP push to audit (ADR-003 relay half). Previously this reported
    backlog only ("libs/events has no relay implementation yet"); the relay itself now
    lives in libs/common/safepayai_common/outbox/relay.py, shared by all 7 producers."""
    _require_tick_secret(x_tick_secret)
    settings = get_settings()
    result = await flush_outbox(session, _relay_config(settings))
    return {
        "delivered": result.delivered,
        "failed": result.failed,
        "pending": result.pending,
    }
