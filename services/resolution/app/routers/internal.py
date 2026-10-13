"""Internal event inbox/outbox + tick endpoints per resolution/api.md section 2.
Never routed by the gateway externally (404 externally is a gateway concern, not ours)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from safepayai_common.auth.jwt import ServiceJWTConfig
from safepayai_common.outbox import OutboxRelayConfig
from safepayai_common.outbox import flush_outbox as relay_flush_outbox
from sqlalchemy.ext.asyncio import AsyncSession

from app import repo
from app.db import get_session
from app.deps import require_internal_jwt, require_tick_secret
from app.domain.states import CaseKind, CaseOrigin
from app.schemas.cases import InternalEventEnvelope
from app.settings import settings
from app.usecases.open_case import OpenCaseCommand
from app.usecases.open_case import open_case as uc_open_case

router = APIRouter(prefix="/internal", tags=["internal"])


def _relay_config() -> OutboxRelayConfig:
    """S2-06: one OutboxRelayConfig per service, built from its own settings -- the relay
    mechanics themselves live in libs/common/safepayai_common/outbox/relay.py (shared)."""
    return OutboxRelayConfig(
        schema="resolution",
        producer="resolution",
        audit_base_url=settings.outbox_relay_audit_base_url,
        jwt=ServiceJWTConfig(
            issuer=settings.outbox_relay_jwt_issuer,
            audience="audit",
            signing_key_pem=settings.outbox_relay_jwt_private_key,
            kid=settings.outbox_relay_jwt_kid,
        ),
        batch_size=settings.outbox_relay_batch_size,
    )


def _not_implemented(endpoint: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=f"{endpoint} pending Wave 5"
    )


_INBOX_KIND_BY_TYPE = {
    "shipment.late_detected": CaseKind.LATE,
    "shipment.lost_detected": CaseKind.LOST,
}


@router.post("/events")
async def internal_events_receive(
    body: InternalEventEnvelope,
    claims: dict = Depends(require_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """api.md section 6 inbox: shipment.late_detected/lost_detected open a DETECTOR-origin
    case (idempotent on (order_id, kind) via open_case) and run the same decide ->
    offer-creation path as a buyer report, skipping triage entirely (spec s3 T5). Deduping
    beyond the (order_id, kind) unique constraint is a no-op per api.md section 6 ("handler
    is a no-op if the case exists"). mandate.revoked is accepted but not yet actioned here
    (future work, see api.md section 6 third inbox row); unknown event types are ignored
    (at-least-once delivery, forward-compatible).
    """
    # Imported lazily to avoid a cases<->internal router import cycle at module load time.
    from app.routers.cases import decide_and_offer

    kind = _INBOX_KIND_BY_TYPE.get(body.type)
    if kind is None:
        return {"ok": True, "handled": False}

    order_id = body.payload.get("order_id")
    if not order_id:
        raise HTTPException(status_code=422, detail="VALIDATION_ERROR")

    opened = await uc_open_case(
        session,
        OpenCaseCommand(
            order_id=UUID(order_id),
            kind=kind,
            origin=CaseOrigin.DETECTOR,
            source_event_id=body.event_id,
            untrusted_text=None,
        ),
    )
    if opened.created:
        await decide_and_offer(session, opened.case_id)
    await session.commit()
    return {"ok": True, "handled": True, "case_id": str(opened.case_id)}


@router.get("/outbox")
async def internal_outbox_pull(
    after: int = 0,
    claims: dict = Depends(require_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """api.md section 2: "S -- Pull catch-up" (ADR-003). Read-only debug/catch-up endpoint
    for a consumer that may have missed outbox rows via the push relay; mirrors
    services/mandate/app/routers/internal.py's outbox_pull shape."""
    rows = await repo.get_outbox_after(session, after=after)
    return {
        "events": [
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
    }


@router.post("/outbox/flush")
async def internal_outbox_flush(
    _: None = Depends(require_tick_secret),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """S2-06: actual HTTP push to audit (ADR-003 relay half)."""
    result = await relay_flush_outbox(session, _relay_config())
    return {
        "delivered": result.delivered,
        "failed": result.failed,
        "pending": result.pending,
    }


@router.post("/tick", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def internal_tick(_: None = Depends(require_tick_secret)) -> None:
    raise _not_implemented("POST /internal/tick")
