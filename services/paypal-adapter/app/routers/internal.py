"""Internal cron endpoint for paypal-adapter -- S2-06 outbox relay.

Guarded by the existing `outbox_flush_secret` setting (PS_PAYPALADAPTER_OUTBOX_FLUSH_SECRET),
matching the shared-secret cron-trigger pattern every other service uses under the bare
INTERNAL_TICK_SECRET name (conventions doc section 2) -- this service already had a
dedicated field for exactly this purpose (app/settings.py), so it is reused rather than
adding a second, redundant secret. Never routed by the gateway (404 externally).

Wired into app/main.py's `app.include_router` block.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException
from safepayai_common.auth.jwt import ServiceJWTConfig
from safepayai_common.outbox import OutboxRelayConfig
from safepayai_common.outbox import flush_outbox as relay_flush_outbox
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.settings import Settings, get_settings

router = APIRouter(prefix="/internal", tags=["internal"])


def _require_flush_secret(x_tick_secret: str | None, settings: Settings) -> None:
    if not x_tick_secret or not settings.outbox_flush_secret:
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")
    if not hmac.compare_digest(x_tick_secret, settings.outbox_flush_secret):
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")


def _relay_config(settings: Settings) -> OutboxRelayConfig:
    """S2-06: one OutboxRelayConfig per service, built from its own settings -- the relay
    mechanics themselves live in libs/common/safepayai_common/outbox/relay.py (shared)."""
    return OutboxRelayConfig(
        schema="paypal",
        producer="paypal-adapter",
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
    x_tick_secret: str | None = Header(default=None),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """S2-06: actual HTTP push to audit (ADR-003 relay half)."""
    _require_flush_secret(x_tick_secret, settings)
    result = await relay_flush_outbox(session, _relay_config(settings))
    return {"delivered": result.delivered, "failed": result.failed, "pending": result.pending}
