"""Order lifecycle endpoints -- api.md sections 5-9.

Wave 5B landed GET /orders/{order_id} and GET /orders for real; POST /orders/return,
POST /orders/cancel, POST /orders/{id}/capture and GET /orders/{id}/receipt were 501
stubs pending paypal-adapter's own create_order/get_order/capture_order endpoints
(S1-08) and the ticket HMAC wiring. paypal-adapter's S1-08 scope landed; this wave wires
checkout's capture path for real (sprint-plan S2-01/S2-02).

Capture core (spec.md section 7 steps 4-10 / section 8-10, api.md section 6) lives in
`_attempt_capture` below and is shared by the return handler, the manual-retry/reconcile
endpoint, and (implicitly) future `/internal/reconcile` work. The ticket minted for the
adapter capture call is still the placeholder established in carts.py's confirm flow
(`ticket=<request id>`) -- full HMAC ticket minting (PS_CHECKOUT_TICKET_HMAC_KEY) is
tracked separately and not yet provisioned in this repo.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app import clients, logic, repo
from app.clients import AdapterResult, UpstreamError
from app.db import get_db
from app.deps import (
    Principal,
    mint_outbound_token,
    require_idempotency_key,
    require_service_jwt,
)
from app.errors import CheckoutError
from app.schemas.carts import OrderCancelRequest, OrderReturnRequest
from app.settings import Settings, get_settings

router = APIRouter(tags=["orders"])

# Terminal order states: immutable, never re-entered by the capture flow (spec.md
# section 3's state machine).
TERMINAL_STATES = {
    "CAPTURED",
    "CAPTURE_FAILED",
    "CANCELLED_REVOKED",
    "CANCELLED_BUYER",
    "CREATE_FAILED",
    "EXPIRED",
}

# States from which a capture attempt is meaningful (api.md section 6).
CAPTURABLE_STATES = {"AWAITING_APPROVAL", "APPROVED", "CAPTURE_UNKNOWN"}


def _buyer_id(principal: Principal) -> str:
    return principal.buyer_id or principal.sub


def _order_view(row: dict) -> dict:
    return {
        "order_id": str(row["order_id"]),
        "cart_id": str(row["cart_id"]),
        "mandate_id": str(row["mandate_id"]),
        "status": row["status"],
        "total_minor": row["total_minor"],
        "currency": row["currency"],
        "paypal_order_id": row["paypal_order_id"],
        "approve_url": row["approve_url"],
        "failure_code": row["failure_code"],
        "created_at": row["created_at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
        "updated_at": row["updated_at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _message_code(status: str) -> str:
    return {
        "CAPTURED": "CAPTURED",
        "CAPTURE_PENDING": "PENDING_PROTECTION_NOT_STARTED",
        "CANCELLED_REVOKED": "MANDATE_REVOKED",
    }.get(status, "TRY_AGAIN")


def _amount_major(minor: int) -> str:
    """Integer-minor-units -> display string, no float at any point (CLAUDE.md money rule)."""
    sign = "-" if minor < 0 else ""
    whole, cents = divmod(abs(int(minor)), 100)
    return f"{sign}{whole}.{cents:02d}"


# ---------------------------------------------------------------------------
# Capture core
# ---------------------------------------------------------------------------


async def _mandate_status(settings: Settings, mandate_id: str) -> dict:
    """spec.md section 7 step 4 / sprint-plan S2-01: sync, authoritative revoke/expire
    check AT THIS MOMENT -- not the cart-creation-time check. Mirrors mandate's own
    authorize-capture pattern (services/mandate/app/routers/reservations.py: "the last
    point where 'stop' could win") by re-checking via mandate's existing GET endpoint
    instead of duplicating any revoke logic here."""
    token = mint_outbound_token(settings, "mandate")
    try:
        return await clients.get_mandate(settings, token, mandate_id)
    except UpstreamError as exc:
        raise CheckoutError(
            503, "MANDATE_UNAVAILABLE", f"mandate check failed: {exc.detail}"
        ) from exc


async def _record_capture_failed(
    session: AsyncSession, order_id: str, mandate_id: str, new_status: str, reason: str
) -> None:
    async with session.begin():
        fresh = await repo.get_order_row(session, order_id)
        if fresh is None or fresh["status"] in TERMINAL_STATES:
            return
        await repo.cas_order_status(
            session, order_id, fresh["version"], new_status, failure_code=reason[:64]
        )
        await repo.insert_outbox_event(
            session,
            event_type="order.capture_failed",
            aggregate_id=order_id,
            payload={
                "order_id": order_id,
                "mandate_id": mandate_id,
                "reason": reason,
                "final_status": new_status,
            },
        )


async def _finalize_captured(
    session: AsyncSession,
    *,
    order_row: dict,
    mandate: dict,
    capture_id: str | None,
    amount_minor: int,
    currency: str,
    custom_id: str | None,
    invoice_id: str | None,
    paypal_status: str | None,
) -> dict:
    """spec.md section 8: one transaction inserts captures, CAS -> CAPTURED, builds and
    inserts the receipt, and emits order.captured. Post-capture custom_id/invoice_id
    assertion mismatch cannot be undone (money already moved) -- it only flags the order
    via failure_code for human follow-up, per spec.md section 8's note."""
    order_id = str(order_row["order_id"])
    mandate_id = str(order_row["mandate_id"])
    captured_at = repo.now_utc()
    mismatch = custom_id != mandate_id or invoice_id != order_id

    async with session.begin():
        fresh = await repo.get_order_row(session, order_id)
        if fresh is None:
            raise CheckoutError(404, "ORDER_NOT_FOUND", "order not found")
        if fresh["status"] == "CAPTURED":
            return {
                "status": "CAPTURED",
                "message_code": "CAPTURED",
                "failure_code": None,
            }

        await repo.insert_capture(
            session,
            capture_id=capture_id or order_id,
            order_id=order_id,
            amount_minor=amount_minor,
            currency=currency,
            paypal_status=paypal_status,
            custom_id=custom_id,
            invoice_id=invoice_id,
            captured_at=captured_at,
        )
        failure_code = "BINDING_MISMATCH" if mismatch else None
        await repo.cas_order_status(
            session, order_id, fresh["version"], "CAPTURED", failure_code=failure_code
        )

        cart_row = await repo.get_cart_row(session, str(fresh["cart_id"]))
        checks = await repo.get_cart_checks(session, str(fresh["cart_id"]))
        event_id = str(uuid.uuid4())
        receipt_json = _build_receipt_json(
            order_row=fresh,
            capture_id=capture_id or order_id,
            amount_minor=amount_minor,
            currency=currency,
            cart_row=cart_row,
            checks=checks,
            mandate=mandate,
            event_id=event_id,
        )
        protection = mandate.get("protection") or {}
        await repo.insert_receipt(
            session,
            order_id=order_id,
            receipt_json=receipt_json,
            mandate_hash=cart_row["mandate_hash"] if cart_row else None,
            audit_event_id=event_id,
            protection_window_days=protection.get("deliver_by_days"),
            remaining_cap_minor=mandate.get("remaining_minor"),
        )
        await repo.insert_outbox_event(
            session,
            event_type="order.captured",
            aggregate_id=order_id,
            payload={
                "order_id": order_id,
                "capture_id": capture_id or order_id,
                "mandate_id": mandate_id,
                "buyer_id": str(fresh["buyer_id"]),
                "amount_minor": amount_minor,
                "currency": currency,
                "captured_at": captured_at.isoformat(),
                "protection_window_days": protection.get("deliver_by_days"),
                "mandate_hash": cart_row["mandate_hash"] if cart_row else None,
            },
            event_id=event_id,
        )
        if mismatch:
            await repo.insert_outbox_event(
                session,
                event_type="order.capture_failed",
                aggregate_id=order_id,
                payload={
                    "order_id": order_id,
                    "mandate_id": mandate_id,
                    "reason": "BINDING_MISMATCH",
                    "final_status": "CAPTURED",
                },
            )

    return {
        "status": "CAPTURED",
        "message_code": "CAPTURED",
        "failure_code": failure_code,
    }


def _build_receipt_json(
    *,
    order_row: dict,
    capture_id: str,
    amount_minor: int,
    currency: str,
    cart_row: dict | None,
    checks: list[dict],
    mandate: dict,
    event_id: str,
) -> dict:
    """api.md section 8 shape + sprint-plan S2-02: major-unit display fields computed
    from the stored integer-minor amount (never float), and the exact disclosure phrase
    "Merchant-funded via PayPal refund" (CLAUDE.md honesty rule -- never PayPal-backed/
    verified, legally binding, non-repudiable, compliant, fraud-proof, injection-proof)."""
    raw_lines = (cart_row or {}).get("lines") or []
    lines_out = []
    for line in raw_lines:
        unit_minor = int(line.get("unit_price_minor", 0))
        line_minor = int(line.get("line_total_minor", 0))
        lines_out.append(
            {
                "sku": line.get("sku"),
                "qty": line.get("qty"),
                "unit_minor": unit_minor,
                "unit_major": _amount_major(unit_minor),
                "line_minor": line_minor,
                "line_major": _amount_major(line_minor),
                "merchant_id": line.get("merchant_id"),
            }
        )

    protection = mandate.get("protection") or {}
    window_days = protection.get("deliver_by_days", 0)
    intent_fit = None
    if cart_row is not None and cart_row.get("intent_fit_verdict"):
        intent_fit = {
            "verdict": cart_row["intent_fit_verdict"],
            "reason_code": cart_row.get("intent_fit_reason_code"),
            "confidence": cart_row.get("intent_fit_confidence"),
            "advisory": True,
            "note": "Advisory AI check; can only tighten; cannot clear a block",
        }

    return {
        "order_id": str(order_row["order_id"]),
        "paypal_order_id": order_row["paypal_order_id"],
        "capture_id": capture_id,
        "status": "CAPTURED",
        "amount_minor": amount_minor,
        "amount_major": _amount_major(amount_minor),
        "currency": currency,
        "lines": lines_out,
        "checks": [
            {
                "name": c["name"],
                "result": c["result"],
                "reason_code": c["reason_code"],
                "source": c["source"],
                "detail": c["detail"],
            }
            for c in checks
        ],
        "intent_fit": intent_fit,
        "mandate": {
            "mandate_id": str(order_row["mandate_id"]),
            "mandate_hash": cart_row["mandate_hash"] if cart_row else None,
        },
        "audit": {"event_id": event_id, "seq": None},
        "remaining_cap_minor": mandate.get("remaining_minor"),
        "protection": {
            "window_days": window_days,
            "protected_until_day": window_days,
            "label": "Demo window, not PayPal's",
        },
        "disclosures": [
            "Sandbox only",
            "Demo protection window is illustrative",
            "Merchant-funded via PayPal refund",
        ],
    }


async def _attempt_capture(
    session: AsyncSession, settings: Settings, order_row: dict
) -> dict:
    """Runs spec.md section 7 steps 4-10 (also section 10's reconcile rules) from the
    current order state. Returns {status, message_code, failure_code, not_approved?}.
    Does NOT do any return-binding validation -- callers (the return handler, the manual
    capture endpoint) own that; this is purely the "re-check mandate, re-check PayPal,
    capture or reconcile" core so it cannot drift between the two call sites.
    """
    order_id = str(order_row["order_id"])
    mandate_id = str(order_row["mandate_id"])

    if order_row["status"] in TERMINAL_STATES:
        return {
            "status": order_row["status"],
            "message_code": _message_code(order_row["status"]),
            "failure_code": order_row.get("failure_code"),
        }

    # Step 4: authoritative revoke/expire check AT CAPTURE TIME, not cart-check time.
    mandate = await _mandate_status(settings, mandate_id)
    mandate_status = mandate.get("status", "active")
    if mandate_status in ("revoked", "expired"):
        await _record_capture_failed(
            session, order_id, mandate_id, "CANCELLED_REVOKED", "MANDATE_REVOKED"
        )
        return {
            "status": "CANCELLED_REVOKED",
            "message_code": "MANDATE_REVOKED",
            "failure_code": "MANDATE_REVOKED",
        }

    paypal_order_id = order_row["paypal_order_id"]
    if not paypal_order_id:
        raise CheckoutError(
            409, "ORDER_NOT_CAPTURABLE", "order has no paypal_order_id yet"
        )

    token = mint_outbound_token(settings, "paypal-adapter")
    get_result = await clients.get_order(settings, token, paypal_order_id)
    if not get_result.ok:
        if get_result.definite:
            await _record_capture_failed(
                session, order_id, mandate_id, "CAPTURE_FAILED", "ORDER_LOOKUP_FAILED"
            )
            return {
                "status": "CAPTURE_FAILED",
                "message_code": "TRY_AGAIN",
                "failure_code": "ORDER_LOOKUP_FAILED",
            }
        # Indefinite lookup failure: leave state untouched, caller/reconcile retries later.
        return {
            "status": order_row["status"],
            "message_code": "TRY_AGAIN",
            "failure_code": None,
        }

    data = get_result.body or {}
    paypal_status = data.get("status")

    if paypal_status == "COMPLETED":
        # Reconcile adoption path (spec.md section 10): PayPal already shows COMPLETED
        # (our own prior capture call timed out, or a duplicate return) -- adopt the
        # existing capture, never call capture_order again.
        capture_ids = data.get("capture_ids") or []
        return await _finalize_captured(
            session,
            order_row=order_row,
            mandate=mandate,
            capture_id=capture_ids[0] if capture_ids else None,
            amount_minor=data.get("amount_minor") or order_row["total_minor"],
            currency=data.get("currency") or order_row["currency"],
            custom_id=data.get("custom_id"),
            invoice_id=data.get("invoice_id"),
            paypal_status="COMPLETED",
        )

    if paypal_status != "APPROVED":
        # Buyer has not approved yet (or order is in some other non-terminal PayPal
        # state) -- not an error on our side, no state change.
        return {
            "status": order_row["status"],
            "message_code": "TRY_AGAIN",
            "failure_code": None,
            "not_approved": True,
        }

    mismatch = (
        data.get("amount_minor") != order_row["total_minor"]
        or data.get("currency") != order_row["currency"]
        or data.get("custom_id") != mandate_id
        or data.get("invoice_id") != order_id
    )
    if mismatch:
        await _record_capture_failed(
            session, order_id, mandate_id, "CAPTURE_FAILED", "ORDER_MISMATCH"
        )
        return {
            "status": "CAPTURE_FAILED",
            "message_code": "TRY_AGAIN",
            "failure_code": "ORDER_MISMATCH",
        }

    async with session.begin():
        cart_row = await repo.get_cart_row(session, str(order_row["cart_id"]))
    proposal_hash = (cart_row or {}).get("proposal_hash") or ""

    # R4: persist CAPTURING + capture_request_id BEFORE the adapter call, same txn.
    # Reconcile retry reuses the SAME capture_request_id, never a new one (spec.md
    # section 10's capture-timeout row).
    capture_request_id = str(order_row.get("capture_request_id") or uuid.uuid4())
    async with session.begin():
        fresh = await repo.get_order_row(session, order_id)
        if fresh is None or fresh["status"] in TERMINAL_STATES:
            return {
                "status": fresh["status"] if fresh else order_row["status"],
                "message_code": _message_code(fresh["status"] if fresh else ""),
                "failure_code": fresh.get("failure_code") if fresh else None,
            }
        capture_request_id = str(fresh.get("capture_request_id") or capture_request_id)
        moved = await repo.cas_order_status(
            session,
            order_id,
            fresh["version"],
            "CAPTURING",
            capture_request_id=capture_request_id,
        )
        if not moved:
            # Lost the CAS race to a concurrent attempt on the same order; re-read and
            # bail without issuing a second adapter call.
            raced = await repo.get_order_row(session, order_id)
            return {
                "status": raced["status"] if raced else fresh["status"],
                "message_code": "TRY_AGAIN",
                "failure_code": None,
            }

    ticket = (
        capture_request_id  # placeholder until PS_CHECKOUT_TICKET_HMAC_KEY wiring lands
    )
    capture_result = await clients.capture_order(
        settings,
        token,
        paypal_order_id=paypal_order_id,
        request_id=capture_request_id,
        mandate_id=mandate_id,
        proposal_hash=proposal_hash,
        amount_minor=order_row["total_minor"],
        currency=order_row["currency"],
        ticket=ticket,
    )
    return await _handle_capture_result(
        session, order_row=order_row, mandate=mandate, capture_result=capture_result
    )


async def _handle_capture_result(
    session: AsyncSession,
    *,
    order_row: dict,
    mandate: dict,
    capture_result: AdapterResult,
) -> dict:
    order_id = str(order_row["order_id"])
    mandate_id = str(order_row["mandate_id"])

    if capture_result.ok:
        data = capture_result.body or {}
        capture_status = data.get("capture_status")
        if capture_status == "COMPLETED":
            return await _finalize_captured(
                session,
                order_row=order_row,
                mandate=mandate,
                capture_id=data.get("capture_id"),
                amount_minor=data.get("amount_minor") or order_row["total_minor"],
                currency=data.get("currency") or order_row["currency"],
                custom_id=data.get("custom_id"),
                invoice_id=data.get("invoice_id"),
                paypal_status=capture_status,
            )
        # spec.md section 9: PENDING (or any other non-error, non-COMPLETED status) --
        # no captures row, no receipt, no order.captured.
        async with session.begin():
            fresh = await repo.get_order_row(session, order_id)
            if fresh is not None and fresh["status"] not in TERMINAL_STATES:
                await repo.cas_order_status(
                    session, order_id, fresh["version"], "CAPTURE_PENDING"
                )
        return {
            "status": "CAPTURE_PENDING",
            "message_code": "PENDING_PROTECTION_NOT_STARTED",
            "failure_code": None,
        }

    # 409 from the adapter: order was not actually APPROVED (race between our get_order
    # pre-check and the capture call). Never a double-capture risk -- just unresolved;
    # reconcile (get_order) sorts it out on the next attempt.
    if capture_result.detail == "not_approved":
        await _record_capture_failed(
            session, order_id, mandate_id, "CAPTURE_UNKNOWN", "RACE_NOT_APPROVED"
        )
        return {
            "status": "CAPTURE_UNKNOWN",
            "message_code": "TRY_AGAIN",
            "failure_code": None,
        }

    if capture_result.definite:
        reason = capture_result.code or "PAYPAL_DECLINED"
        await _record_capture_failed(
            session, order_id, mandate_id, "CAPTURE_FAILED", reason
        )
        return {
            "status": "CAPTURE_FAILED",
            "message_code": "TRY_AGAIN",
            "failure_code": reason,
        }

    # Indefinite (timeout/5xx/202 IN_PROGRESS/malformed): CAPTURE_UNKNOWN. Never
    # recaptured blindly -- the next attempt reconciles via get_order first.
    async with session.begin():
        fresh = await repo.get_order_row(session, order_id)
        if fresh is not None and fresh["status"] not in TERMINAL_STATES:
            await repo.cas_order_status(
                session,
                order_id,
                fresh["version"],
                "CAPTURE_UNKNOWN",
                failure_code=capture_result.detail[:64],
            )
    return {
        "status": "CAPTURE_UNKNOWN",
        "message_code": "TRY_AGAIN",
        "failure_code": None,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/orders/return")
async def orders_return(
    body: OrderReturnRequest,
    principal: Principal = Depends(require_service_jwt),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    buyer_id = _buyer_id(principal)
    state_hash = logic.sha256_hex(body.state.encode("utf-8"))

    async with session.begin():
        binding = await repo.get_return_binding(session, state_hash)
    if binding is None or binding["kind"] != "return":
        raise CheckoutError(400, "STATE_INVALID", "return state missing or wrong kind")
    now = repo.now_utc()
    exp = binding["exp"]
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=now.tzinfo)
    if exp < now:
        raise CheckoutError(400, "STATE_INVALID", "return state expired")
    if str(binding["buyer_id"]) != buyer_id:
        raise CheckoutError(
            403, "BUYER_MISMATCH", "buyer does not own this return state"
        )

    async with session.begin():
        order_row = await repo.get_order_row(session, str(binding["order_id"]))
    if order_row is None:
        raise CheckoutError(404, "ORDER_NOT_FOUND", "order not found")

    if binding["used_at"] is not None:
        # Duplicate return: idempotent if it's the same order, else a real conflict.
        if order_row["paypal_order_id"] == body.token:
            return _return_response(order_row)
        raise CheckoutError(
            409,
            "STATE_ALREADY_USED_OTHER_ORDER",
            "state already consumed for a different order",
        )

    if order_row["paypal_order_id"] != body.token:
        raise CheckoutError(
            400, "TOKEN_MISMATCH", "token does not match stored paypal order id"
        )

    async with session.begin():
        consumed = await repo.mark_return_binding_used(session, state_hash)
    if not consumed:
        # Raced with a concurrent consumer of the same state; current DB state wins.
        async with session.begin():
            fresh = await repo.get_order_row(session, str(binding["order_id"]))
        return _return_response(fresh or order_row)

    outcome = await _attempt_capture(session, settings, order_row)
    if outcome.get("not_approved"):
        async with session.begin():
            await repo.clear_return_binding_used(session, state_hash)
        raise CheckoutError(409, "NOT_APPROVED", "buyer has not approved on PayPal yet")

    async with session.begin():
        final_row = await repo.get_order_row(session, str(binding["order_id"]))
    response = _return_response(final_row or order_row, outcome)
    if outcome["status"] == "CANCELLED_REVOKED":
        raise CheckoutError(
            422,
            "MANDATE_REVOKED",
            "mandate was revoked before capture",
            {"order_id": response["order_id"]},
        )
    return response


def _return_response(order_row: dict, outcome: dict | None = None) -> dict:
    status = order_row["status"]
    message_code = (outcome or {}).get("message_code") or _message_code(status)
    return {
        "order_id": str(order_row["order_id"]),
        "status": status,
        "receipt_url": f"/orders/{order_row['order_id']}/receipt",
        "message_code": message_code,
    }


@router.post("/orders/cancel")
async def orders_cancel(
    body: OrderCancelRequest,
    principal: Principal = Depends(require_service_jwt),
    session: AsyncSession = Depends(get_db),
) -> dict:
    buyer_id = _buyer_id(principal)
    state_hash = logic.sha256_hex(body.state.encode("utf-8"))

    async with session.begin():
        binding = await repo.get_return_binding(session, state_hash)
    if binding is None or binding["kind"] != "cancel":
        raise CheckoutError(400, "STATE_INVALID", "cancel state missing or wrong kind")
    if str(binding["buyer_id"]) != buyer_id:
        raise CheckoutError(
            403, "BUYER_MISMATCH", "buyer does not own this cancel state"
        )

    async with session.begin():
        order_row = await repo.get_order_row(session, str(binding["order_id"]))
    if order_row is None:
        raise CheckoutError(404, "ORDER_NOT_FOUND", "order not found")

    async with session.begin():
        await repo.mark_return_binding_used(session, state_hash)
        fresh = await repo.get_order_row(session, str(binding["order_id"]))
        if fresh is not None and fresh["status"] in ("CREATING", "AWAITING_APPROVAL"):
            await repo.cas_order_status(
                session, str(binding["order_id"]), fresh["version"], "CANCELLED_BUYER"
            )
            fresh = await repo.get_order_row(session, str(binding["order_id"]))

    final_row = fresh or order_row
    return {"order_id": str(final_row["order_id"]), "status": final_row["status"]}


@router.post("/orders/{order_id}/capture")
async def capture_order_endpoint(
    order_id: str,
    principal: Principal = Depends(require_service_jwt),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    idempotency_key: str = Depends(require_idempotency_key),
) -> dict:
    """api.md section 6: idempotent retry/reconcile entry, identical checks to
    POST /orders/return, from the current order state. Used for the manual fallback if
    the browser redirect never reached our server, and by future reconcile tooling."""
    principal_key = _buyer_id(principal) if principal.role == "buyer" else principal.sub

    async with session.begin():
        existing = await repo.idempotency_lookup(
            session, principal_key, "POST /orders/capture", idempotency_key
        )
    if existing is not None:
        return dict(existing["response_body"])

    async with session.begin():
        order_row = await repo.get_order_row(session, order_id)
    if order_row is None:
        raise CheckoutError(404, "ORDER_NOT_FOUND", "order not found")
    if principal.role == "buyer" and str(order_row["buyer_id"]) != principal_key:
        raise CheckoutError(404, "ORDER_NOT_FOUND", "order not found")

    if (
        order_row["status"] not in CAPTURABLE_STATES
        and order_row["status"] != "CAPTURED"
    ):
        raise CheckoutError(
            409, "ORDER_NOT_CAPTURABLE", f"order status is {order_row['status']}"
        )

    outcome = await _attempt_capture(session, settings, order_row)

    async with session.begin():
        final_row = await repo.get_order_row(session, order_id)
    response_body = _order_view(final_row or order_row)

    status_code = 200
    error_code: str | None = None
    if outcome["status"] == "CANCELLED_REVOKED":
        status_code, error_code = 422, "MANDATE_REVOKED"
    elif outcome.get("not_approved"):
        status_code, error_code = 409, "NOT_APPROVED"

    async with session.begin():
        await repo.idempotency_store(
            session,
            principal_key,
            "POST /orders/capture",
            idempotency_key,
            repo.request_hash_of({"order_id": order_id}),
            status_code,
            response_body,
        )

    if error_code is not None:
        raise CheckoutError(
            status_code, error_code, "capture did not complete", {"order_id": order_id}
        )
    return response_body


@router.get("/orders/{order_id}")
async def get_order(
    order_id: str,
    principal: Principal = Depends(require_service_jwt),
    session: AsyncSession = Depends(get_db),
) -> dict:
    async with session.begin():
        row = await repo.get_order_row(session, order_id)
    if row is None:
        raise CheckoutError(404, "ORDER_NOT_FOUND", "order not found")
    if principal.role == "buyer" and str(row["buyer_id"]) != _buyer_id(principal):
        raise CheckoutError(404, "ORDER_NOT_FOUND", "order not found")
    return _order_view(row)


@router.get("/orders/{order_id}/receipt")
async def get_receipt(
    order_id: str,
    principal: Principal = Depends(require_service_jwt),
    session: AsyncSession = Depends(get_db),
) -> dict:
    async with session.begin():
        order_row = await repo.get_order_row(session, order_id)
    if order_row is None:
        raise CheckoutError(404, "ORDER_NOT_FOUND", "order not found")
    if principal.role == "buyer" and str(order_row["buyer_id"]) != _buyer_id(principal):
        raise CheckoutError(404, "ORDER_NOT_FOUND", "order not found")
    if order_row["status"] != "CAPTURED":
        raise CheckoutError(
            409,
            "RECEIPT_NOT_READY",
            f"order status is {order_row['status']}, not CAPTURED",
        )
    async with session.begin():
        receipt_row = await repo.get_receipt_row(session, order_id)
    if receipt_row is None:
        raise CheckoutError(
            404, "RECEIPT_NOT_FOUND", "receipt not found for this order"
        )
    return dict(receipt_row["receipt_json"])


@router.get("/orders")
async def list_orders(
    mandate_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    principal: Principal = Depends(require_service_jwt),
    session: AsyncSession = Depends(get_db),
) -> dict:
    if mandate_id is None:
        raise CheckoutError(
            422, "VALIDATION_ERROR", "mandate_id query param is required"
        )
    async with session.begin():
        from sqlalchemy import text

        query = "SELECT * FROM checkout.orders WHERE mandate_id = :mandate_id"
        params: dict[str, object] = {"mandate_id": mandate_id}
        if status is not None:
            query += " AND status = :status"
            params["status"] = status
        result = await session.execute(text(query), params)
        rows = [dict(r) for r in result.mappings().all()]
    buyer_id = _buyer_id(principal)
    if principal.role == "buyer":
        rows = [r for r in rows if str(r["buyer_id"]) == buyer_id]
    return {"items": [_order_view(r) for r in rows]}
