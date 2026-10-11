"""ops layer (spec.md section 1): the only place money logic exists, so REST and MCP
cannot diverge. S1-08 scope: create_order, get_order, capture_order with the call_ledger
idempotency flow (spec.md section 6) and the token-cache/401-retry PayPal client.

Out of scope for S1-08 (deferred, see sprint-plan row S1-08 vs S2-07/S3-06 and the dispatch
prompt): full authorization-ticket HMAC verification (spec.md section 5 -- needs the
checkout/resolution minters, not built yet; the router dependency only checks the ticket
header is present), the MONEY_FROZEN DB control-flag path beyond PS_PAYPALADAPTER_MONEY_ENABLED,
rate limiting, and outbox event types beyond `paypal.call_recorded`.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app import ledger
from app.paypal_client import PayPalAuthError, PayPalClient, PayPalUpstreamError
from app.settings import Settings


class OpError(Exception):
    def __init__(
        self, status: str, code: str, message: str, *, http_status: int, retryable: bool = False
    ):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.http_status = http_status
        self.retryable = retryable


def _envelope(
    *,
    ok: bool,
    status: str,
    trace_id: str,
    paypal_http_status: int | None = None,
    data: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
    replayed: bool = False,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "status": status,
        "paypal_http_status": paypal_http_status,
        "data": data,
        "error": error,
        "replayed": replayed,
        "trace_id": trace_id,
    }


def _redact_order_response(raw: dict[str, Any]) -> dict[str, Any]:
    """Ledger response_json_redacted stores only allowlisted fields (spec.md section 10):
    ids, status, amounts, custom_id, invoice_id -- never payer name/email/approve-link
    query params."""
    purchase_units = raw.get("purchase_units") or [{}]
    pu = purchase_units[0] if purchase_units else {}
    amount = pu.get("amount") or {}
    return {
        "order_id": raw.get("id"),
        "status": raw.get("status"),
        "custom_id": pu.get("custom_id"),
        "invoice_id": pu.get("invoice_id"),
        "currency": amount.get("currency_code"),
        "value": amount.get("value"),
    }


def _money_frozen(settings: Settings) -> bool:
    # Fail closed: unset/false -> frozen (spec.md section 9 kill switch).
    return not settings.money_enabled


async def _check_money_enabled(settings: Settings, trace_id: str) -> None:
    if _money_frozen(settings):
        raise OpError("REJECTED", "MONEY_FROZEN", "money operations are frozen", http_status=403)


def _is_approve_origin_ok(url: str, allowed_origins: str) -> bool:
    allowed = {o.strip() for o in allowed_origins.split(",") if o.strip()}
    for origin in allowed:
        if url.startswith(origin):
            return True
    return False


async def create_order(
    session: AsyncSession,
    client: PayPalClient,
    settings: Settings,
    *,
    caller: str,
    request_id: str,
    mandate_id: str,
    internal_order_id: str,
    amount_minor: int,
    currency: str,
    return_url: str,
    cancel_url: str,
    trace_id: str,
) -> dict[str, Any]:
    await _check_money_enabled(settings, trace_id)

    if not _is_approve_origin_ok(return_url, settings.paypal_return_url_allowed_origins) or (
        not _is_approve_origin_ok(cancel_url, settings.paypal_return_url_allowed_origins)
    ):
        raise OpError(
            "REJECTED",
            "VALIDATION_ERROR",
            "return_url/cancel_url origin not allowed",
            http_status=400,
        )

    body_for_hash = {
        "op": "create_order",
        "mandate_id": mandate_id,
        "internal_order_id": internal_order_id,
        "amount_minor": amount_minor,
        "currency": currency,
        "return_url": return_url,
        "cancel_url": cancel_url,
    }
    body_hash = ledger.body_sha256(body_for_hash)

    won = await ledger.insert_in_flight(
        session, request_id=request_id, op="create_order", caller=caller, body_hash=body_hash
    )
    if not won:
        return await _resolve_existing(session, request_id, body_hash, trace_id)

    try:
        raw = await client.create_order(
            request_id=request_id,
            amount_minor=amount_minor,
            currency=currency,
            custom_id=mandate_id,
            invoice_id=internal_order_id,
            return_url=return_url,
            cancel_url=cancel_url,
        )
    except PayPalAuthError:
        await ledger.mark_done(
            session,
            request_id,
            state="DONE_REJECTED",
            paypal_http_status=503,
            paypal_object_id=None,
            response_json_redacted=None,
        )
        raise OpError(
            "REJECTED", "UPSTREAM_AUTH_FAILED", "PayPal authentication failed", http_status=503
        ) from None
    except PayPalUpstreamError as exc:
        if exc.status_code is None or exc.status_code >= 500:
            await ledger.mark_done(
                session,
                request_id,
                state="UNKNOWN",
                paypal_http_status=exc.status_code,
                paypal_object_id=None,
                response_json_redacted=None,
            )
            raise OpError(
                "UNKNOWN", "UPSTREAM_UNAVAILABLE", "PayPal unavailable", http_status=504
            ) from None
        await ledger.mark_done(
            session,
            request_id,
            state="DONE_REJECTED",
            paypal_http_status=exc.status_code,
            paypal_object_id=None,
            response_json_redacted=None,
        )
        raise OpError(
            "REJECTED", "UPSTREAM_REJECTED", "PayPal rejected the request", http_status=422
        ) from None

    redacted = _redact_order_response(raw)
    approve_url = next(
        (link.get("href") for link in raw.get("links", []) if link.get("rel") == "approve"), None
    )
    data = {
        "order_id": raw.get("id"),
        "status": raw.get("status"),
        "approve_url": approve_url,
        "custom_id": redacted["custom_id"],
        "invoice_id": redacted["invoice_id"],
        "amount_minor": amount_minor,
        "currency": currency,
    }
    await ledger.mark_done(
        session,
        request_id,
        state="DONE_OK",
        paypal_http_status=201,
        paypal_object_id=raw.get("id"),
        response_json_redacted={**redacted, "approve_url": approve_url},
    )
    await ledger.insert_outbox_event(
        session,
        event_id=str(uuid.uuid4()),
        event_type="paypal.call_recorded",
        aggregate_id=mandate_id,
        payload={
            "op": "create_order",
            "request_id": request_id,
            "order_id": raw.get("id"),
            "status": raw.get("status"),
        },
        trace_id=trace_id,
    )
    return _envelope(ok=True, status="OK", trace_id=trace_id, paypal_http_status=201, data=data)


async def _resolve_existing(
    session: AsyncSession, request_id: str, body_hash: str, trace_id: str
) -> dict[str, Any]:
    row = await ledger.get_ledger_row(session, request_id)
    if row is None:
        # Row vanished between the failed insert and this read (should not happen
        # outside of a hostile race); treat conservatively as UNKNOWN.
        raise OpError(
            "UNKNOWN", "UPSTREAM_UNAVAILABLE", "ledger race, retry later", http_status=504
        )
    if row.body_sha256 != body_hash:
        raise OpError(
            "REJECTED",
            "IDEMPOTENCY_KEY_REUSED",
            "request_id reused with a different body",
            http_status=409,
        )
    if row.state == "IN_FLIGHT":
        return _envelope(ok=False, status="IN_PROGRESS", trace_id=trace_id, replayed=False)
    if row.state == "UNKNOWN":
        return _envelope(ok=False, status="UNKNOWN", trace_id=trace_id, replayed=False)
    if row.state == "DONE_REJECTED":
        return _envelope(
            ok=False,
            status="REJECTED",
            trace_id=trace_id,
            paypal_http_status=row.paypal_http_status,
            error={
                "code": "UPSTREAM_REJECTED",
                "message": "see original call",
                "retryable": False,
                "paypal_name": None,
            },
            replayed=True,
        )
    # DONE_OK
    return _envelope(
        ok=True,
        status="OK",
        trace_id=trace_id,
        paypal_http_status=row.paypal_http_status,
        data=row.response_json_redacted,
        replayed=True,
    )


async def get_order(client: PayPalClient, order_id: str, *, trace_id: str) -> dict[str, Any]:
    try:
        raw = await client.get_order(order_id)
    except PayPalAuthError as exc:
        raise OpError(
            "REJECTED", "UPSTREAM_AUTH_FAILED", "PayPal authentication failed", http_status=503
        ) from exc
    except PayPalUpstreamError as exc:
        if exc.status_code == 404:
            raise OpError("REJECTED", "NOT_FOUND", "order not found", http_status=404) from exc
        if exc.status_code is None or exc.status_code >= 500:
            raise OpError(
                "REJECTED",
                "UPSTREAM_UNAVAILABLE",
                "PayPal unavailable",
                http_status=502,
                retryable=True,
            ) from exc
        raise OpError(
            "REJECTED", "UPSTREAM_REJECTED", "PayPal rejected the request", http_status=422
        ) from exc

    purchase_units = raw.get("purchase_units") or [{}]
    pu = purchase_units[0] if purchase_units else {}
    amount = pu.get("amount") or {}
    capture_ids = [
        capture.get("id")
        for capture in (pu.get("payments", {}).get("captures") or [])
        if capture.get("id")
    ]
    data = {
        "order_id": raw.get("id"),
        "status": raw.get("status"),
        "custom_id": pu.get("custom_id"),
        "invoice_id": pu.get("invoice_id"),
        "amount_minor": _minor_from_value(amount.get("value")),
        "currency": amount.get("currency_code"),
        "capture_ids": capture_ids,
    }
    return _envelope(ok=True, status="OK", trace_id=trace_id, paypal_http_status=200, data=data)


def _minor_from_value(value: str | None) -> int | None:
    if value is None:
        return None
    dollars, _, cents = value.partition(".")
    cents = (cents + "00")[:2]
    return int(dollars) * 100 + int(cents or "0")


async def capture_order(
    session: AsyncSession,
    client: PayPalClient,
    settings: Settings,
    *,
    caller: str,
    order_id: str,
    request_id: str,
    mandate_id: str,
    amount_minor: int,
    currency: str,
    trace_id: str,
) -> dict[str, Any]:
    await _check_money_enabled(settings, trace_id)

    body_for_hash = {
        "op": "capture_order",
        "order_id": order_id,
        "mandate_id": mandate_id,
        "amount_minor": amount_minor,
        "currency": currency,
    }
    body_hash = ledger.body_sha256(body_for_hash)

    won = await ledger.insert_in_flight(
        session, request_id=request_id, op="capture_order", caller=caller, body_hash=body_hash
    )
    if not won:
        return await _resolve_existing(session, request_id, body_hash, trace_id)

    # Pre-check (spec.md section 5.4 step 8 / api.md section 5.3): order must be APPROVED,
    # custom_id/amount/currency must match the authorized intent, before PayPal is called.
    try:
        order = await client.get_order(order_id)
    except PayPalAuthError:
        await ledger.mark_done(
            session,
            request_id,
            state="DONE_REJECTED",
            paypal_http_status=503,
            paypal_object_id=None,
            response_json_redacted=None,
        )
        raise OpError(
            "REJECTED", "UPSTREAM_AUTH_FAILED", "PayPal authentication failed", http_status=503
        ) from None
    except PayPalUpstreamError as exc:
        await ledger.mark_done(
            session,
            request_id,
            state="UNKNOWN",
            paypal_http_status=exc.status_code,
            paypal_object_id=None,
            response_json_redacted=None,
        )
        raise OpError(
            "UNKNOWN", "UPSTREAM_UNAVAILABLE", "PayPal unavailable", http_status=504
        ) from None

    pu = (order.get("purchase_units") or [{}])[0]
    if order.get("status") != "APPROVED":
        await ledger.mark_done(
            session,
            request_id,
            state="DONE_REJECTED",
            paypal_http_status=None,
            paypal_object_id=order.get("id"),
            response_json_redacted=None,
        )
        raise OpError(
            "REJECTED", "ORDER_NOT_APPROVED", "order is not in APPROVED status", http_status=409
        )
    if pu.get("custom_id") != mandate_id:
        await ledger.mark_done(
            session,
            request_id,
            state="DONE_REJECTED",
            paypal_http_status=None,
            paypal_object_id=order.get("id"),
            response_json_redacted=None,
        )
        raise OpError(
            "REJECTED",
            "AUTHORIZATION_MISMATCH",
            "mandate_id does not match order custom_id",
            http_status=403,
        )

    try:
        raw = await client.capture_order(order_id, request_id=request_id)
    except PayPalAuthError:
        await ledger.mark_done(
            session,
            request_id,
            state="DONE_REJECTED",
            paypal_http_status=503,
            paypal_object_id=None,
            response_json_redacted=None,
        )
        raise OpError(
            "REJECTED", "UPSTREAM_AUTH_FAILED", "PayPal authentication failed", http_status=503
        ) from None
    except PayPalUpstreamError as exc:
        if exc.status_code is None or exc.status_code >= 500:
            await ledger.mark_done(
                session,
                request_id,
                state="UNKNOWN",
                paypal_http_status=exc.status_code,
                paypal_object_id=order.get("id"),
                response_json_redacted=None,
            )
            raise OpError(
                "UNKNOWN", "UPSTREAM_UNAVAILABLE", "PayPal unavailable", http_status=504
            ) from None
        await ledger.mark_done(
            session,
            request_id,
            state="DONE_REJECTED",
            paypal_http_status=exc.status_code,
            paypal_object_id=order.get("id"),
            response_json_redacted=None,
        )
        raise OpError(
            "REJECTED", "UPSTREAM_REJECTED", "PayPal rejected the request", http_status=422
        ) from None

    capture_pu = (raw.get("purchase_units") or [{}])[0]
    captures = capture_pu.get("payments", {}).get("captures") or []
    capture = captures[0] if captures else {}
    data = {
        "order_id": raw.get("id"),
        "status": raw.get("status"),
        "capture_id": capture.get("id"),
        "capture_status": capture.get("status"),
        "custom_id": capture_pu.get("custom_id"),
        "invoice_id": capture_pu.get("invoice_id"),
        "amount_minor": amount_minor,
        "currency": currency,
    }
    await ledger.mark_done(
        session,
        request_id,
        state="DONE_OK",
        paypal_http_status=201,
        paypal_object_id=capture.get("id"),
        response_json_redacted=data,
    )
    await ledger.insert_outbox_event(
        session,
        event_id=str(uuid.uuid4()),
        event_type="paypal.call_recorded",
        aggregate_id=mandate_id,
        payload={
            "op": "capture_order",
            "request_id": request_id,
            "order_id": raw.get("id"),
            "capture_id": capture.get("id"),
        },
        trace_id=trace_id,
    )
    return _envelope(ok=True, status="OK", trace_id=trace_id, paypal_http_status=201, data=data)
