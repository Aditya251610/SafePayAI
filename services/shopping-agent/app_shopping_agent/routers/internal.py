"""/internal/outbox/* -- api.md section 7. Never routed by the gateway."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException
from safepayai_common.auth.jwt import ServiceJWTConfig
from safepayai_common.outbox import OutboxRelayConfig
from safepayai_common.outbox import flush_outbox as relay_flush_outbox
from sqlalchemy.ext.asyncio import AsyncSession

from app_shopping_agent import persistence
from app_shopping_agent.db import get_db
from app_shopping_agent.deps import ServicePrincipal, require_service_jwt
from app_shopping_agent.settings import Settings, get_settings

router = APIRouter(prefix="/internal", tags=["internal"])


def _relay_config(settings: Settings) -> OutboxRelayConfig:
    """S2-06: one OutboxRelayConfig per service, built from its own settings -- the relay
    mechanics themselves live in libs/common/safepayai_common/outbox/relay.py (shared)."""
    return OutboxRelayConfig(
        schema="agent",
        producer="shopping-agent",
        audit_base_url=settings.outbox_relay_audit_base_url,
        jwt=ServiceJWTConfig(
            issuer=settings.outbox_relay_jwt_issuer,
            audience="audit",
            signing_key_pem=settings.outbox_relay_jwt_private_key,
            kid=settings.outbox_relay_jwt_kid,
        ),
        batch_size=settings.outbox_relay_batch_size,
    )


def _require_tick_secret(x_tick_secret: str | None, settings: Settings) -> None:
    """`/internal/outbox/flush` is driven by the scheduled-workflow cron caller (S2-06),
    matching mandate/checkout/tracking/resolution's INTERNAL_TICK_SECRET convention
    (conventions doc section 2) rather than require_service_jwt's live-JWKS check."""
    if not x_tick_secret or not settings.internal_tick_secret:
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")
    if not hmac.compare_digest(x_tick_secret, settings.internal_tick_secret):
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")


@router.post("/outbox/flush")
async def outbox_flush(
    x_tick_secret: str | None = Header(default=None),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """S2-06: actual HTTP push to audit (ADR-003 relay half)."""
    _require_tick_secret(x_tick_secret, settings)
    result = await relay_flush_outbox(session, _relay_config(settings))
    return {
        "delivered": result.delivered,
        "failed": result.failed,
        "pending": result.pending,
    }


@router.get("/outbox")
async def read_outbox(
    after: int = 0,
    _principal: ServicePrincipal = Depends(require_service_jwt),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """api.md section 7: pull catch-up (ADR-003) -- read-only, debug/backfill only."""
    events = await persistence.get_outbox_after(session, after=after)
    return {"events": events}
