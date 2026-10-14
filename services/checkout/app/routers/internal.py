"""/internal/* -- api.md section 10. Never routed by the gateway.

POST /internal/events, GET /internal/outbox, and POST /internal/reconcile are real now.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException
from safepayai_common.auth.jwt import ServiceJWTConfig
from safepayai_common.outbox import OutboxRelayConfig
from safepayai_common.outbox import flush_outbox as relay_flush_outbox
from sqlalchemy.ext.asyncio import AsyncSession

from app import repo
from app.db import get_db
from app.deps import Principal, require_service_jwt
from app.routers.orders import _attempt_capture
from app.schemas.internal import InboundEvent
from app.settings import Settings, get_settings

router = APIRouter(prefix="/internal", tags=["internal"])


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
    which would require a JWKS endpoint this standalone cron trigger doesn't have.

    hmac.compare_digest, not `!=` -- matches tracking/resolution's own require_tick_secret
    (a `!=` comparison on secrets is a timing side-channel)."""
    if not x_tick_secret or not settings.internal_tick_secret:
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")
    if not hmac.compare_digest(x_tick_secret, settings.internal_tick_secret):
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")


@router.post("/events")
async def internal_events(
    body: InboundEvent,
    _principal: Principal = Depends(require_service_jwt),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """api.md section 10: handles `mandate.revoked` (blocks un-captured carts under that
    mandate; non-terminal pre-capture orders are re-checked organically by their own
    capture-time live mandate lookup, _attempt_capture/_mandate_status, no separate flag
    needed). 200 duplicate-safe via the `inbox` dedupe table. Unknown event types are a
    no-op (at-least-once delivery, forward-compatible, same convention as resolution's
    inbox handler)."""
    if body.version != 1:
        raise HTTPException(status_code=400, detail="UNSUPPORTED_EVENT_VERSION")

    async with session.begin():
        is_new = await repo.inbox_event_is_new(session, body.event_id, body.type)
        if not is_new:
            return {"ok": True, "handled": False, "duplicate": True}

        if body.type != "mandate.revoked":
            return {"ok": True, "handled": False}

        mandate_id = body.payload.get("mandate_id")
        if not mandate_id:
            raise HTTPException(status_code=422, detail="VALIDATION_ERROR")
        blocked = await repo.block_carts_for_mandate(session, str(mandate_id))

    return {"ok": True, "handled": True, "carts_blocked": blocked}


@router.get("/outbox")
async def read_outbox(
    after: int = 0,
    _principal: Principal = Depends(require_service_jwt),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """api.md section 10: pull catch-up (ADR-003) -- read-only, debug/backfill only."""
    events = await repo.get_outbox_after(session, after=after)
    return {"events": events}


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


@router.post("/reconcile")
async def reconcile(
    _principal: Principal = Depends(require_service_jwt),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """api.md section 10: `POST /internal/reconcile -> {"examined", "advanced", "unchanged",
    "errors": []}`, safe to repeat. Re-runs _attempt_capture (the same core the buyer-facing
    return/manual-capture endpoints use, spec s7 steps 4-10) against every order stuck in a
    CAPTURABLE_STATES status -- a buyer who approved on PayPal but never completed the
    return redirect (closed the tab, lost connection) would otherwise sit there forever."""
    examined = 0
    advanced = 0
    unchanged = 0
    errors: list[dict[str, str]] = []

    async with session.begin():
        stuck_orders = await repo.get_non_terminal_orders(session)
    for stuck in stuck_orders:
        examined += 1
        order_id = str(stuck["order_id"])
        try:
            # Each read gets its own explicit, closed transaction -- SQLAlchemy's
            # autobegin would otherwise leave an implicit transaction open across this
            # bare read, which then collides with _attempt_capture's own explicit
            # session.begin() ("a transaction is already begun on this Session").
            # _attempt_capture itself manages its own internal transactions (same as
            # every existing caller -- the return handler, the manual capture endpoint --
            # never wraps it in an outer session.begin()).
            async with session.begin():
                order_row = await repo.get_order_row(session, order_id)
            if order_row is None:
                continue
            before_status = order_row["status"]
            outcome = await _attempt_capture(session, settings, order_row)
            if outcome["status"] != before_status:
                advanced += 1
            else:
                unchanged += 1
        except Exception as exc:  # noqa: BLE001 - reconcile must not abort on one bad order
            errors.append({"order_id": order_id, "error": str(exc)})

    return {
        "examined": examined,
        "advanced": advanced,
        "unchanged": unchanged,
        "errors": errors,
    }
