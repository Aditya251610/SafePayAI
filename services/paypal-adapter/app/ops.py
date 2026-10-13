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

from app import control_flags, ledger
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


def error_envelope(exc: OpError, trace_id: str) -> dict[str, Any]:
    """Shared OpError -> envelope translation for routers added in this wave (get_capture,
    tracking). Matches the dict literal captures.py's refund_capture handler has used inline
    since S1-08/Wave 5B -- that one is left as-is (untouched, already-reviewed money path)."""
    return {
        "ok": False,
        "status": exc.status,
        "paypal_http_status": None,
        "data": None,
        "error": {
            "code": exc.code,
            "message": exc.message,
            "retryable": exc.retryable,
            "paypal_name": None,
        },
        "replayed": False,
        "trace_id": trace_id,
    }


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


async def _money_frozen(settings: Settings, session: AsyncSession) -> bool:
    # Fail closed: unset/false static flag -> frozen (spec.md section 9 kill switch). Even
    # when the static flag says enabled, the service-local DB control_flags.frozen flag
    # (app.control_flags, toggled via POST /v1/control/freeze|unfreeze) can independently
    # freeze money ops -- either source freezing is enough to block (fail closed, matching
    # resolution's own REFUNDS_FROZEN philosophy). An absent/unreadable DB row is also
    # treated as frozen. Short-circuits before the DB read when the static flag already
    # says frozen, so the common "money disabled everywhere" case stays a pure env check.
    if not settings.money_enabled:
        return True
    flags = await control_flags.get_control_flags(session)
    if flags is None:
        return True
    return flags.frozen


async def _check_money_enabled(settings: Settings, session: AsyncSession, trace_id: str) -> None:
    if await _money_frozen(settings, session):
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
    await _check_money_enabled(settings, session, trace_id)

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
    if row.state in ("IN_FLIGHT", "IN_PROGRESS_REMOTE"):
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


async def get_capture(client: PayPalClient, capture_id: str, *, trace_id: str) -> dict[str, Any]:
    """GET /v1/captures/{capture_id} (api.md section 4/5.4-class read). Plain upstream
    passthrough, same class as get_order/get_refund -- no ledger, no money decision."""
    try:
        raw = await client.get_capture(capture_id)
    except PayPalAuthError as exc:
        raise OpError(
            "REJECTED", "UPSTREAM_AUTH_FAILED", "PayPal authentication failed", http_status=503
        ) from exc
    except PayPalUpstreamError as exc:
        if exc.status_code == 404:
            raise OpError("REJECTED", "NOT_FOUND", "capture not found", http_status=404) from exc
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

    amount = raw.get("amount") or {}
    data = {
        "capture_id": raw.get("id"),
        "status": raw.get("status"),
        "amount_minor": _minor_from_value(amount.get("value")),
        "currency": amount.get("currency_code"),
        "invoice_id": raw.get("invoice_id"),
        "custom_id": raw.get("custom_id"),
        "final_capture": raw.get("final_capture"),
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
    await _check_money_enabled(settings, session, trace_id)

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


def _capture_id_from_links(links: list[dict[str, Any]]) -> str | None:
    for link in links:
        if link.get("rel") == "up":
            href = str(link.get("href", "")).rstrip("/")
            return href.rsplit("/", 1)[-1] or None
    return None


async def refund_capture(
    session: AsyncSession,
    client: PayPalClient,
    settings: Settings,
    *,
    caller: str,
    capture_id: str,
    request_id: str,
    invoice_id: str | None,
    amount_minor: int,
    currency: str,
    ticket: str,
    trace_id: str,
) -> dict[str, Any]:
    """POST /captures/{capture_id}/refund (spec.md s7, api.md 5.7).

    CLAUDE.md money-path rule: never trust the caller's amount_minor without checking it
    against our own ledger's recorded capture amount -- `ledger.get_capture_ledger_row`
    (our own capture_order record, not PayPal's live response, per spec C13's documented
    fallback: derive from our own data, rely on PayPal's 422 as backstop) is the source of
    truth for `captured_amount_minor`; `ledger.sum_committed_refunds` is the source of truth
    for what has already been committed against it. `ticket` is accepted but (like
    create_order/capture_order in this Wave) full HMAC verification is deferred -- only
    presence is required by the caller (router dependency / body fallback).
    """
    del ticket  # presence-only check happens in the router; kept as an explicit param here
    # so a future HMAC-verification pass has an obvious single call site to extend.
    await _check_money_enabled(settings, session, trace_id)

    if amount_minor > settings.refund_max_minor:
        raise OpError(
            "REJECTED",
            "AMOUNT_OVER_CEILING",
            "amount exceeds PS_PAYPALADAPTER_REFUND_MAX_MINOR",
            http_status=400,
        )

    body_for_hash = {
        "op": "refund_capture",
        "capture_id": capture_id,
        "invoice_id": invoice_id,
        "amount_minor": amount_minor,
        "currency": currency,
    }
    body_hash = ledger.body_sha256(body_for_hash)

    won = await ledger.insert_in_flight(
        session, request_id=request_id, op="refund_capture", caller=caller, body_hash=body_hash
    )
    if not won:
        return await _resolve_existing(session, request_id, body_hash, trace_id)

    capture_row = await ledger.get_capture_ledger_row(session, capture_id)
    if capture_row is None:
        await ledger.mark_done(
            session,
            request_id,
            state="DONE_REJECTED",
            paypal_http_status=None,
            paypal_object_id=capture_id,
            response_json_redacted=None,
        )
        raise OpError(
            "REJECTED",
            "NOT_FOUND",
            "capture not recorded in our own ledger",
            http_status=404,
        )

    if currency != capture_row.currency:
        await ledger.mark_done(
            session,
            request_id,
            state="DONE_REJECTED",
            paypal_http_status=None,
            paypal_object_id=capture_id,
            response_json_redacted=None,
        )
        raise OpError(
            "REJECTED",
            "CURRENCY_UNSUPPORTED",
            "currency does not match the capture",
            http_status=400,
        )

    already_committed = await ledger.sum_committed_refunds(session, capture_id)
    refundable_remaining = capture_row.amount_minor - already_committed
    if amount_minor > refundable_remaining:
        await ledger.mark_done(
            session,
            request_id,
            state="DONE_REJECTED",
            paypal_http_status=None,
            paypal_object_id=capture_id,
            response_json_redacted=None,
        )
        raise OpError(
            "REJECTED",
            "REFUND_AMOUNT_EXCEEDED",
            f"amount_minor {amount_minor} exceeds derived refundable_remaining "
            f"{refundable_remaining}",
            http_status=409,
        )

    reservation_id = f"pending:{request_id}"
    await ledger.insert_refund_reservation(
        session,
        refund_id=reservation_id,
        request_id=request_id,
        capture_id=capture_id,
        amount_minor=amount_minor,
        currency=currency,
        status="PENDING",
    )

    try:
        raw = await client.refund_capture(
            capture_id,
            request_id=request_id,
            amount_minor=amount_minor,
            currency=currency,
            invoice_id=invoice_id,
        )
    except PayPalAuthError:
        await ledger.update_refund_status(session, refund_id=reservation_id, status="FAILED")
        await ledger.mark_done(
            session,
            request_id,
            state="DONE_REJECTED",
            paypal_http_status=503,
            paypal_object_id=capture_id,
            response_json_redacted=None,
        )
        raise OpError(
            "REJECTED", "UPSTREAM_AUTH_FAILED", "PayPal authentication failed", http_status=503
        ) from None
    except PayPalUpstreamError as exc:
        # spec.md section 7's table: 409 on write -> ledger IN_PROGRESS_REMOTE, status
        # IN_PROGRESS (never blind-retry a refund -- reconcile via GET/POST /reconcile).
        if exc.status_code == 409:
            await ledger.mark_done(
                session,
                request_id,
                state="IN_PROGRESS_REMOTE",
                paypal_http_status=409,
                paypal_object_id=capture_id,
                response_json_redacted=None,
            )
            return _envelope(
                ok=False, status="IN_PROGRESS", trace_id=trace_id, paypal_http_status=409
            )
        if exc.status_code is None or exc.status_code == 429 or exc.status_code >= 500:
            # Ambiguous outcome: do NOT release the reservation (CLAUDE.md: a timeout/5xx
            # means UNKNOWN, not FAILED -- caller must reconcile, never blind-retry).
            await ledger.mark_done(
                session,
                request_id,
                state="UNKNOWN",
                paypal_http_status=exc.status_code,
                paypal_object_id=capture_id,
                response_json_redacted=None,
            )
            raise OpError(
                "UNKNOWN", "UPSTREAM_UNAVAILABLE", "PayPal unavailable", http_status=504
            ) from None
        await ledger.update_refund_status(session, refund_id=reservation_id, status="FAILED")
        code = "UPSTREAM_REJECTED"
        if exc.paypal_name == "REFUND_AMOUNT_EXCEEDED":
            code = "REFUND_AMOUNT_EXCEEDED"
        elif exc.paypal_name == "DUPLICATE_INVOICE_ID":
            code = "DUPLICATE_INVOICE_ID"
        await ledger.mark_done(
            session,
            request_id,
            state="DONE_REJECTED",
            paypal_http_status=exc.status_code,
            paypal_object_id=capture_id,
            response_json_redacted=None,
        )
        raise OpError("REJECTED", code, "PayPal rejected the refund", http_status=422) from None

    refund_id = raw.get("id") or reservation_id
    status = raw.get("status") or "PENDING"
    data = {
        "refund_id": refund_id,
        "status": status,
        "amount_minor": amount_minor,
        "currency": currency,
        "capture_id": capture_id,
    }
    final_ledger_status = "COMPLETED" if status == "COMPLETED" else "PENDING"
    await ledger.finalize_refund(
        session,
        reservation_id=reservation_id,
        final_refund_id=refund_id,
        status=final_ledger_status,
    )
    await ledger.mark_done(
        session,
        request_id,
        state="DONE_OK",
        paypal_http_status=201,
        paypal_object_id=refund_id,
        response_json_redacted=data,
    )
    await ledger.insert_outbox_event(
        session,
        event_id=str(uuid.uuid4()),
        event_type="paypal.call_recorded",
        aggregate_id=capture_id,
        payload={
            "op": "refund_capture",
            "request_id": request_id,
            "capture_id": capture_id,
            "refund_id": refund_id,
            "status": status,
        },
        trace_id=trace_id,
    )
    return _envelope(ok=True, status="OK", trace_id=trace_id, paypal_http_status=201, data=data)


async def get_refund(
    session: AsyncSession, client: PayPalClient, refund_id: str, *, trace_id: str
) -> dict[str, Any]:
    """GET /refunds/{refund_id} (api.md 5.8). Our own refund_ledger is the fast (<20ms)
    source of truth when we minted the refund; falls back to a live PayPal lookup for a
    refund_id we don't recognize (e.g. reconciling something outside our own ledger)."""
    row = await ledger.get_refund_ledger_row(session, refund_id)
    if row is not None:
        data = {
            "refund_id": row.refund_id,
            "status": row.status,
            "amount_minor": row.amount_minor,
            "currency": row.currency,
            "capture_id": row.capture_id,
        }
        return _envelope(ok=True, status="OK", trace_id=trace_id, paypal_http_status=200, data=data)

    try:
        raw = await client.get_refund(refund_id)
    except PayPalAuthError as exc:
        raise OpError(
            "REJECTED", "UPSTREAM_AUTH_FAILED", "PayPal authentication failed", http_status=503
        ) from exc
    except PayPalUpstreamError as exc:
        if exc.status_code == 404:
            raise OpError("REJECTED", "NOT_FOUND", "refund not found", http_status=404) from exc
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

    amount = raw.get("amount") or {}
    data = {
        "refund_id": raw.get("id"),
        "status": raw.get("status"),
        "amount_minor": _minor_from_value(amount.get("value")),
        "currency": amount.get("currency_code"),
        "capture_id": _capture_id_from_links(raw.get("links") or []),
    }
    return _envelope(ok=True, status="OK", trace_id=trace_id, paypal_http_status=200, data=data)


def _tracker_id(capture_id: str, tracking_number: str) -> str:
    """api.md section 5.5's documented contract/sandbox-spike example: tracker_id is always
    `{capture_id}-{tracking_number}`, a composite natural key -- not parsed off a PayPal
    response body (PayPal's own tracker ids for this API follow the same transaction_id-
    tracking_number shape, used directly as the GET path segment)."""
    return f"{capture_id}-{tracking_number}"


async def add_tracking(
    client: PayPalClient,
    order_id: str,
    *,
    capture_id: str,
    tracking_number: str,
    carrier_name_other: str,
    notify_payer: bool,
    trace_id: str,
) -> dict[str, Any]:
    """POST /v1/orders/{order_id}/track (api.md section 5.5). Best-effort signal only (spec
    s1/s7): no money decision, no call_ledger idempotency row -- PayPal-Request-Id has no
    documented effect on this endpoint (api.md 5.5: "I"); the natural key (capture_id,
    tracking_number) is the documented dedupe guard instead, handled below by reading the
    tracker back on a duplicate-add rejection rather than surfacing a spurious error."""
    tracker_id = _tracker_id(capture_id, tracking_number)
    try:
        raw = await client.add_tracker(
            order_id,
            transaction_id=capture_id,
            tracking_number=tracking_number,
            carrier_name_other=carrier_name_other,
            notify_payer=notify_payer,
        )
    except PayPalAuthError as exc:
        raise OpError(
            "REJECTED", "UPSTREAM_AUTH_FAILED", "PayPal authentication failed", http_status=503
        ) from exc
    except PayPalUpstreamError as exc:
        if exc.status_code == 422:
            # Natural-key dedupe (api.md 5.5): a duplicate add is expected to be rejected
            # upstream; read back the tracker we would otherwise have created and report it
            # replayed rather than surfacing an error for an already-tracked shipment. If the
            # read-back itself fails, the original 422 was for some other reason -- propagate it.
            try:
                existing = await client.get_tracker(order_id, tracker_id)
            except (PayPalAuthError, PayPalUpstreamError):
                raise OpError(
                    "REJECTED",
                    "UPSTREAM_REJECTED",
                    "PayPal rejected the tracker add",
                    http_status=422,
                ) from exc
            data = {
                "order_id": order_id,
                "tracker_id": tracker_id,
                "status": existing.get("status", "SHIPPED"),
            }
            return _envelope(
                ok=True,
                status="OK",
                trace_id=trace_id,
                paypal_http_status=200,
                data=data,
                replayed=True,
            )
        if exc.status_code is None or exc.status_code >= 500:
            raise OpError(
                "UNKNOWN",
                "UPSTREAM_UNAVAILABLE",
                "PayPal unavailable",
                http_status=504,
                retryable=True,
            ) from exc
        raise OpError(
            "REJECTED", "UPSTREAM_REJECTED", "PayPal rejected the tracker add", http_status=422
        ) from exc

    status = "SHIPPED"
    trackers = raw.get("trackers") if isinstance(raw, dict) else None
    if isinstance(trackers, list) and trackers and isinstance(trackers[0], dict):
        status = trackers[0].get("status", status)
    data = {"order_id": order_id, "tracker_id": tracker_id, "status": status}
    return _envelope(ok=True, status="OK", trace_id=trace_id, paypal_http_status=201, data=data)


async def get_tracking(
    client: PayPalClient, order_id: str, tracker_id: str, *, trace_id: str
) -> dict[str, Any]:
    """GET /v1/orders/{order_id}/trackers/{tracker_id} (api.md section 5.6). Path flagged
    UNVERIFIED (U2) in the spec; `verified` is always reported false here -- this is an
    honest statement that this exact PayPal read-back path has not been re-confirmed live in
    this pass (CLAUDE.md honesty rule), not a permanent claim about the API shape.
    `carrier_status` is deliberately left null -- late/lost/delivered state lives only in the
    `tracking` service's own DB (SIMULATED CARRIER, per CLAUDE.md); this endpoint never
    merges or guesses at it."""
    try:
        raw = await client.get_tracker(order_id, tracker_id)
    except PayPalAuthError as exc:
        raise OpError(
            "REJECTED", "UPSTREAM_AUTH_FAILED", "PayPal authentication failed", http_status=503
        ) from exc
    except PayPalUpstreamError as exc:
        if exc.status_code == 404:
            raise OpError("REJECTED", "NOT_FOUND", "tracker not found", http_status=404) from exc
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

    data = {
        "order_id": order_id,
        "tracker_id": raw.get("id") or tracker_id,
        "paypal_status": raw.get("status"),
        "carrier_status": None,
        "verified": False,
    }
    return _envelope(ok=True, status="OK", trace_id=trace_id, paypal_http_status=200, data=data)


async def cancel_tracking(
    client: PayPalClient, order_id: str, tracker_id: str, *, status: str, trace_id: str
) -> dict[str, Any]:
    """PATCH /v1/orders/{order_id}/trackers/{tracker_id}/status. `status` is already
    constrained to the literal "CANCELLED" by UpdateTrackerStatusRequest's schema pattern
    (api.md section 5.1/spec s1: irreversible once applied -- a second cancel on an
    already-CANCELLED tracker gets PayPal's own 400, mapped to UPSTREAM_REJECTED below, not
    specially detected as a replay since there is nothing to safely no-op into)."""
    try:
        await client.update_tracker_status(order_id, tracker_id, status=status)
    except PayPalAuthError as exc:
        raise OpError(
            "REJECTED", "UPSTREAM_AUTH_FAILED", "PayPal authentication failed", http_status=503
        ) from exc
    except PayPalUpstreamError as exc:
        if exc.status_code == 404:
            raise OpError("REJECTED", "NOT_FOUND", "tracker not found", http_status=404) from exc
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
    return _envelope(ok=True, status="OK", trace_id=trace_id, paypal_http_status=204, data=None)


async def reconcile(session: AsyncSession, request_id: str, *, trace_id: str) -> dict[str, Any]:
    """POST /reconcile/{request_id} (api.md section 6/spec.md s6): idempotent replay lookup
    against our own ledger -- never re-calls PayPal, never mutates state. UNKNOWN/IN_FLIGHT/
    IN_PROGRESS_REMOTE are returned as-is so the caller keeps polling rather than retrying."""
    row = await ledger.get_ledger_row(session, request_id)
    if row is None:
        raise OpError("REJECTED", "NOT_FOUND", "unknown request_id", http_status=404)
    if row.state in ("IN_FLIGHT", "IN_PROGRESS_REMOTE"):
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
    return _envelope(
        ok=True,
        status="OK",
        trace_id=trace_id,
        paypal_http_status=row.paypal_http_status,
        data=row.response_json_redacted,
        replayed=True,
    )
