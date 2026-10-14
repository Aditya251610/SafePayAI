"""POST /v1/webhooks/paypal -- optional, PS_PAYPALADAPTER_WEBHOOK_ENABLED=false default
(api.md section 4; deployment.md section 5). Hint only, never authoritative.

Disabled by default: returns a clear `{"ok": false, "status": "DISABLED"}` (200, not a 501
or 404) rather than pretending to process webhooks this deployment was never configured to
receive (CLAUDE.md honesty rule). When enabled, verifies the signature via PayPal's own
documented POST /v1/notifications/verify-webhook-signature API (never a home-grown HMAC
check, per CLAUDE.md) before recording anything.

Verified live (2026-10-14): registered a real sandbox webhook subscription via PayPal's own
REST API, exposed this endpoint through a temporary public tunnel, approved a real checkout,
and confirmed PayPal delivered a genuine `CHECKOUT.ORDER.APPROVED` transmission that this
handler verified successfully (200 OK) -- the subscription and tunnel were torn down
immediately after; this path stays disabled by default as documented above. api.md section 9
only approves `paypal.call_recorded` as an event type so far (`paypal.hint_received` is
proposed, not confirmed) -- a verified webhook receipt is folded into `paypal.call_recorded`
rather than emitting an unapproved event type.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import ledger
from app.db import get_db
from app.paypal_client import (
    PayPalAuthError,
    PayPalClient,
    PayPalUpstreamError,
    get_paypal_client,
)
from app.settings import Settings, get_settings

router = APIRouter(prefix="/v1", tags=["webhooks"])

_REQUIRED_HEADERS = (
    "paypal-auth-algo",
    "paypal-cert-url",
    "paypal-transmission-id",
    "paypal-transmission-sig",
    "paypal-transmission-time",
)


def _trace_id(request: Request) -> str:
    return request.headers.get("X-Trace-Id") or str(uuid.uuid4())


@router.post("/webhooks/paypal")
async def paypal_webhook(
    request: Request,
    settings: Settings = Depends(get_settings),
    client: PayPalClient = Depends(get_paypal_client),
    session: AsyncSession = Depends(get_db),
) -> JSONResponse:
    trace_id = _trace_id(request)

    if not settings.webhook_enabled:
        return JSONResponse(
            status_code=200,
            content={"ok": False, "status": "DISABLED", "trace_id": trace_id},
        )
    if not settings.paypal_webhook_id:
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "status": "MISCONFIGURED",
                "error": {
                    "code": "WEBHOOK_ID_MISSING",
                    "message": "PS_PAYPALADAPTER_PAYPAL_WEBHOOK_ID is not set",
                    "retryable": False,
                },
                "trace_id": trace_id,
            },
        )

    raw_body = await request.body()
    try:
        webhook_event: Any = json.loads(raw_body) if raw_body else {}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="INVALID_BODY") from exc
    if not isinstance(webhook_event, dict):
        raise HTTPException(status_code=400, detail="INVALID_BODY")

    header_values = {name: request.headers.get(name) for name in _REQUIRED_HEADERS}
    missing = [name for name, value in header_values.items() if not value]
    if missing:
        raise HTTPException(status_code=400, detail=f"MISSING_HEADERS:{','.join(missing)}")

    try:
        result = await client.verify_webhook_signature(
            auth_algo=header_values["paypal-auth-algo"],  # type: ignore[arg-type]
            cert_url=header_values["paypal-cert-url"],  # type: ignore[arg-type]
            transmission_id=header_values["paypal-transmission-id"],  # type: ignore[arg-type]
            transmission_sig=header_values["paypal-transmission-sig"],  # type: ignore[arg-type]
            transmission_time=header_values["paypal-transmission-time"],  # type: ignore[arg-type]
            webhook_id=settings.paypal_webhook_id,
            webhook_event=webhook_event,
        )
    except PayPalAuthError as exc:
        raise HTTPException(status_code=503, detail="UPSTREAM_AUTH_FAILED") from exc
    except PayPalUpstreamError as exc:
        status_code = 502 if (exc.status_code is None or exc.status_code >= 500) else 422
        raise HTTPException(status_code=status_code, detail="UPSTREAM_ERROR") from exc

    verification_status = result.get("verification_status")
    if verification_status != "SUCCESS":
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "status": "REJECTED",
                "error": {
                    "code": "SIGNATURE_INVALID",
                    "message": "webhook signature verification failed",
                    "retryable": False,
                },
                "trace_id": trace_id,
            },
        )

    event_type = str(webhook_event.get("event_type", "UNKNOWN"))
    resource = webhook_event.get("resource")
    resource_id = resource.get("id") if isinstance(resource, dict) else None

    await ledger.insert_outbox_event(
        session,
        event_id=str(uuid.uuid4()),
        event_type="paypal.call_recorded",
        aggregate_id=str(resource_id) if resource_id else None,
        payload={
            "op": "webhook_received",
            "event_type": event_type,
            "verification_status": verification_status,
        },
        trace_id=trace_id,
    )

    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "status": "OK",
            "data": {"event_type": event_type},
            "trace_id": trace_id,
        },
    )
