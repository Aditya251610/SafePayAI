"""Internal cron endpoints for tracking -- S2-06 outbox relay.

Guarded by INTERNAL_TICK_SECRET (shared bare name, conventions doc section 2), matching
app/deps.py's existing `require_tick_secret` used by app/routers/detector.py's tick endpoint.
Never routed by the gateway (404 externally).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from safepayai_common.auth.jwt import ServiceJWTConfig
from safepayai_common.outbox import OutboxRelayConfig
from safepayai_common.outbox import flush_outbox as relay_flush_outbox
from sqlalchemy.ext.asyncio import AsyncSession

from app_tracking.db import get_session
from app_tracking.deps import require_tick_secret
from app_tracking.settings import settings

router = APIRouter(prefix="/internal", tags=["internal"])


def _relay_config() -> OutboxRelayConfig:
    """S2-06: one OutboxRelayConfig per service, built from its own settings -- the relay
    mechanics themselves live in libs/common/safepayai_common/outbox/relay.py (shared)."""
    return OutboxRelayConfig(
        schema="tracking",
        producer="tracking",
        audit_base_url=settings.outbox_relay_audit_base_url,
        jwt=ServiceJWTConfig(
            issuer=settings.outbox_relay_jwt_issuer,
            audience="audit",
            signing_key_pem=settings.outbox_relay_jwt_private_key,
            kid=settings.outbox_relay_jwt_kid,
        ),
        batch_size=settings.outbox_relay_batch_size,
    )


@router.post("/outbox/flush")
async def outbox_flush(
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
