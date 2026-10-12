"""/internal/* -- api.md section 10. Never routed by the gateway.

Wave 4: validated stubs, 501.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from safepayai_common.auth.jwt import ServiceJWTConfig
from safepayai_common.outbox import OutboxRelayConfig
from safepayai_common.outbox import flush_outbox as relay_flush_outbox
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import Principal, require_service_jwt
from app.schemas.internal import InboundEvent
from app.settings import Settings, get_settings

router = APIRouter(prefix="/internal", tags=["internal"])


def _not_implemented(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={"error": "not_implemented", "detail": detail, "request_id": None},
    )


def _relay_config(settings: Settings) -> OutboxRelayConfig:
    """S2-06: one OutboxRelayConfig per service, built from its own settings -- the relay
    mechanics themselves live in libs/common/safepayai_common/outbox/relay.py (shared)."""
    return OutboxRelayConfig(
        schema="checkout",
        producer="checkout",
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
    not a service-to-service call -- matches mandate/tracking/resolution's INTERNAL_TICK_SECRET
    convention (conventions doc section 2) rather than require_service_jwt's live-JWKS check,
    which would require a JWKS endpoint this standalone cron trigger doesn't have."""
    if (
        not settings.internal_tick_secret
        or x_tick_secret != settings.internal_tick_secret
    ):
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")


@router.post("/events", status_code=501)
async def internal_events(
    body: InboundEvent,
    _principal: Principal = Depends(require_service_jwt),
) -> JSONResponse:
    return _not_implemented("POST /internal/events pending Wave 5")


@router.get("/outbox", status_code=501)
async def read_outbox(
    after: int = 0,
    _principal: Principal = Depends(require_service_jwt),
) -> JSONResponse:
    return _not_implemented("GET /internal/outbox pending Wave 5")


@router.post("/outbox/flush")
async def outbox_flush(
    x_tick_secret: str | None = Header(default=None),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """S2-06: actual HTTP push to audit (ADR-003 relay half), via the shared relay in
    libs/common/safepayai_common/outbox/relay.py."""
    _require_tick_secret(x_tick_secret, settings)
    result = await relay_flush_outbox(session, _relay_config(settings))
    return {
        "delivered": result.delivered,
        "failed": result.failed,
        "pending": result.pending,
    }


@router.post("/reconcile", status_code=501)
async def reconcile(
    _principal: Principal = Depends(require_service_jwt),
) -> JSONResponse:
    return _not_implemented("POST /internal/reconcile pending Wave 5")
