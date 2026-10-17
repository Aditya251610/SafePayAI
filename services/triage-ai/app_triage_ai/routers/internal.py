"""Internal cron endpoint for triage-ai -- S2-06 outbox relay.

Guarded by INTERNAL_TICK_SECRET (shared bare name, conventions doc section 2). Never routed
by the gateway (404 externally).

NOTE (flagged, not silently resolved): app/deps.py's docstring says triage-ai makes "No
outbound calls to other services from this file or anywhere in this service (ADR-010 /
service-map 'no outbound service calls')". auth-gateway.md section 3.2's caller/callee
matrix explicitly grants `triage -> audit: Y(write own events)`, and triage-ai's own
migrations/versions/0001_baseline.py docstring says `triage.outbox` was added "required by
ADR-003 for an event producer" -- i.e. triage-ai is expected to be an outbox producer, which
is meaningless without ever delivering those rows somewhere. Treating the audit push (pure
telemetry, not a business/money call to another domain service) as the narrow, already-
documented exception the auth matrix grants, consistent with every other producer in this
repo (including shopping-agent, the other ADR-010 LLM-key holder, which also pushes to
audit). If this reading is wrong, the deps.py docstring and the auth matrix disagree and
need reconciling by whoever owns ADR-010's scope -- flagged in the S2-06 PR, not resolved
unilaterally here.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException
from safepayai_common.auth.jwt import ServiceJWTConfig
from safepayai_common.outbox import OutboxRelayConfig
from safepayai_common.outbox import flush_outbox as relay_flush_outbox
from sqlalchemy.ext.asyncio import AsyncSession

from app_triage_ai.db import get_session
from app_triage_ai.settings import settings

router = APIRouter(prefix="/internal", tags=["internal"])


def _require_tick_secret(x_tick_secret: str | None) -> None:
    if not x_tick_secret or not settings.internal_tick_secret:
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")
    if not hmac.compare_digest(x_tick_secret, settings.internal_tick_secret):
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")


def _relay_config() -> OutboxRelayConfig:
    """S2-06: one OutboxRelayConfig per service, built from its own settings -- the relay
    mechanics themselves live in libs/common/safepayai_common/outbox/relay.py (shared)."""
    return OutboxRelayConfig(
        schema="triage",
        producer="triage-ai",
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
    session: AsyncSession = Depends(get_session),
) -> dict:
    """S2-06: actual HTTP push to audit (ADR-003 relay half)."""
    _require_tick_secret(x_tick_secret)
    result = await relay_flush_outbox(session, _relay_config())
    return {
        "delivered": result.delivered,
        "failed": result.failed,
        "pending": result.pending,
    }
