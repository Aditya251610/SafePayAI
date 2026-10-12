"""Internal event inbox/outbox + tick endpoints per resolution/api.md section 2.
Never routed by the gateway externally (404 externally is a gateway concern, not ours)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from safepayai_common.auth.jwt import ServiceJWTConfig
from safepayai_common.outbox import OutboxRelayConfig
from safepayai_common.outbox import flush_outbox as relay_flush_outbox
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import require_internal_jwt, require_tick_secret
from app.schemas.cases import InternalEventEnvelope
from app.settings import settings

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


@router.post("/events", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def internal_events_receive(
    body: InternalEventEnvelope,
    claims: dict = Depends(require_internal_jwt),
) -> None:
    raise _not_implemented("POST /internal/events")


@router.get("/outbox", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def internal_outbox_pull(
    after: int = 0, claims: dict = Depends(require_internal_jwt)
) -> None:
    raise _not_implemented("GET /internal/outbox")


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
