"""POST /carts, GET /carts/{cart_id}, POST /carts/{cart_id}/confirm -- api.md sections 3-4,
spec.md section 4 (cart check pipeline) and section 5 (order creation).

Scope note (Wave 5B / sprint-plan S1-09): intent-fit (spec.md section 4 step 8) is NOT
called here -- shopping-agent's live `/intent-fit` endpoint is S2-05, a later wave (this
wave's shopping-agent scope is only the eval harness). Cart status is therefore derived
from hard blocks only (CHECKED/BLOCKED); NEEDS_CONFIRMATION is reserved for when
intent-fit lands. This is a deliberate, documented scope cut, not an oversight.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app import clients, logic, repo
from app.clients import UpstreamError
from app.db import get_db
from app.deps import (
    Principal,
    mint_outbound_token,
    require_idempotency_key,
    require_service_jwt,
)
from app.errors import CheckoutError
from app.schemas.carts import (
    CartCheck,
    CartLineOut,
    ConfirmCartRequest,
    ConfirmCartResponse,
    CreateCartRequest,
    CreateCartResponse,
)
from app.settings import Settings, get_settings

router = APIRouter(tags=["carts"])


def _buyer_id(principal: Principal) -> str:
    bid = principal.buyer_id or principal.sub
    if not bid:
        raise CheckoutError(401, "UNAUTHENTICATED", "no buyer identity on token")
    return bid


async def _run_check_pipeline(
    settings: Settings,
    buyer_id: str,
    body: CreateCartRequest,
) -> tuple[list[logic.CheckResult], dict | None, dict | None]:
    """Runs spec.md section 4 steps 1-7. Returns (checks, priced, mandate_eval)."""
    checks: list[logic.CheckResult] = []

    # Dedupe SKUs by merging (step 2).
    merged: dict[str, int] = {}
    for line in body.lines:
        merged[line.sku] = merged.get(line.sku, 0) + line.qty

    token = mint_outbound_token(settings, "catalog")
    try:
        priced = await clients.resolve_prices(
            settings, token, [{"sku": sku, "qty": qty} for sku, qty in merged.items()]
        )
    except UpstreamError as exc:
        checks.append(
            logic.CheckResult(
                "catalog_resolve", "BLOCK", "CATALOG_UNAVAILABLE", "catalog", exc.detail
            )
        )
        return checks, None, None

    checks.append(logic.CheckResult("catalog_resolve", "PASS", None, "catalog"))

    # step 4: client-stated prices are never trusted; mismatch is a hard block.
    stated_mismatch = False
    if body.stated_unit_prices_minor:
        for priced_line in priced["lines"]:
            stated = body.stated_unit_prices_minor.get(priced_line["sku"])
            if stated is not None and stated != priced_line["unit_price_minor"]:
                stated_mismatch = True
    if stated_mismatch:
        checks.append(
            logic.CheckResult(
                "price_mismatch",
                "BLOCK",
                "PRICE_MISMATCH",
                "checkout",
                "client-stated unit price differs from catalog price",
            )
        )
    else:
        checks.append(logic.CheckResult("price_mismatch", "PASS", None, "checkout"))

    token = mint_outbound_token(settings, "mandate")
    cart_for_eval = {
        "lines": [
            {
                "sku": line_["sku"],
                "qty": line_["qty"],
                "unit_price_minor": line_["unit_price_minor"],
                "merchant_id": line_["merchant_id"],
            }
            for line_ in priced["lines"]
        ],
        "total_minor": priced["total_minor"],
        "currency": priced["currency"],
        "committed_minor": 0,
    }
    try:
        mandate_eval = await clients.evaluate_mandate(
            settings, token, body.mandate_id, cart_for_eval
        )
    except UpstreamError as exc:
        checks.append(
            logic.CheckResult(
                "mandate_evaluate",
                "BLOCK",
                "MANDATE_UNAVAILABLE",
                "mandate",
                exc.detail,
            )
        )
        return checks, priced, None

    if mandate_eval.get("decision") != "ALLOW":
        reasons = mandate_eval.get("hard_blocks") or ["MANDATE_UNAVAILABLE"]
        for reason in reasons:
            checks.append(
                logic.CheckResult("mandate_evaluate", "BLOCK", reason, "mandate")
            )
    else:
        checks.append(logic.CheckResult("mandate_evaluate", "PASS", None, "mandate"))

    return checks, priced, mandate_eval


@router.post("/carts", status_code=201, response_model=CreateCartResponse)
async def create_cart(
    body: CreateCartRequest,
    principal: Principal = Depends(require_service_jwt),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CreateCartResponse:
    buyer_id = _buyer_id(principal)
    checks, priced, mandate_eval = await _run_check_pipeline(settings, buyer_id, body)

    status = logic.combine_status(checks, intent_fit_verdict=None)

    if priced is not None:
        total_minor = priced["total_minor"]
        currency = priced["currency"]
        lines_out = priced["lines"]
        merchant_ids = priced["merchant_ids"]
        catalog_version = priced["catalog_version"]
    else:
        total_minor = 0
        currency = settings.currency
        lines_out = []
        merchant_ids = []
        catalog_version = None

    mandate_hash = (mandate_eval or {}).get("mandate", {}).get("mandate_hash", "")
    proposal_hash = logic.compute_proposal_hash(
        mandate_id=body.mandate_id,
        mandate_hash=mandate_hash,
        lines=lines_out,
        total_minor=total_minor,
        currency=currency,
        merchant_ids=merchant_ids,
        policy_version=(mandate_eval or {}).get("mandate", {}).get("policy_version"),
    )

    cart_id = str(uuid.uuid4())
    now = datetime.now(UTC)

    async with session.begin():
        # BLOCKED carts still get a positive total_minor fallback so the CHECK
        # constraint (`total_minor > 0`) is not violated; a blocked cart's total is
        # not authoritative for anything downstream (confirm re-runs the pipeline).
        await repo.insert_cart(
            session,
            cart_id=cart_id,
            buyer_id=buyer_id,
            mandate_id=body.mandate_id,
            mandate_hash=mandate_hash or "unknown",
            status=status,
            lines=lines_out,
            total_minor=max(total_minor, 1),
            currency=currency,
            merchant_ids=merchant_ids,
            catalog_version=str(catalog_version)
            if catalog_version is not None
            else None,
            proposal_hash=proposal_hash,
            stated_price_mismatch=any(
                c.reason_code == "PRICE_MISMATCH" for c in checks
            ),
            committed_minor_at_check=None,
        )
        for check in checks:
            await repo.insert_cart_check(
                session,
                cart_id=cart_id,
                phase="CHECK",
                name=check.name,
                result=check.result,
                reason_code=check.reason_code,
                detail=check.detail,
                source=check.source,
            )
        await repo.insert_outbox_event(
            session,
            event_type="cart.checked",
            aggregate_id=cart_id,
            payload={
                "cart_id": cart_id,
                "status": status,
                "mandate_id": body.mandate_id,
            },
        )

    response_lines = [
        CartLineOut(
            sku=line_["sku"],
            qty=line_["qty"],
            unit_minor=line_["unit_price_minor"],
            line_minor=line_["line_total_minor"],
            merchant_id=line_["merchant_id"],
        )
        for line_ in lines_out
    ]

    return CreateCartResponse(
        cart_id=cart_id,
        status=status,  # type: ignore[arg-type]
        currency=currency,
        lines=response_lines,
        total_minor=total_minor,
        remaining_cap_minor_after=(mandate_eval or {})
        .get("mandate", {})
        .get("remaining_minor", 0),
        proposal_hash=proposal_hash,
        checks=[
            CartCheck(
                name=c.name,
                result=c.result,  # type: ignore[arg-type]
                reason_code=c.reason_code,
                source=c.source,
            )
            for c in checks
        ],
        intent_fit=None,
        expires_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


@router.get("/carts/{cart_id}")
async def get_cart(
    cart_id: str,
    principal: Principal = Depends(require_service_jwt),
    session: AsyncSession = Depends(get_db),
) -> dict:
    async with session.begin():
        row = await repo.get_cart_row(session, cart_id)
    if row is None:
        raise CheckoutError(404, "CART_NOT_FOUND", "cart not found")
    if principal.role == "buyer" and str(row["buyer_id"]) != _buyer_id(principal):
        raise CheckoutError(404, "CART_NOT_FOUND", "cart not found")
    return {
        "cart_id": str(row["cart_id"]),
        "status": row["status"],
        "currency": row["currency"],
        "lines": row["lines"],
        "total_minor": row["total_minor"],
        "proposal_hash": row["proposal_hash"],
        "created_at": row["created_at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@router.post("/carts/{cart_id}/confirm", status_code=201)
async def confirm_cart(
    cart_id: str,
    body: ConfirmCartRequest,
    principal: Principal = Depends(require_service_jwt),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    idempotency_key: str = Depends(require_idempotency_key),
    authorization: str | None = Header(default=None),
) -> ConfirmCartResponse:
    buyer_id = _buyer_id(principal)

    async with session.begin():
        existing = await repo.idempotency_lookup(
            session, buyer_id, "POST /carts/confirm", idempotency_key
        )
        if existing is not None:
            return ConfirmCartResponse(**existing["response_body"])

    async with session.begin():
        cart_row = await repo.get_cart_row(session, cart_id)
    if cart_row is None:
        raise CheckoutError(404, "CART_NOT_FOUND", "cart not found")
    if str(cart_row["buyer_id"]) != buyer_id:
        raise CheckoutError(404, "CART_NOT_FOUND", "cart not found")
    if cart_row["status"] not in ("CHECKED", "NEEDS_CONFIRMATION"):
        raise CheckoutError(
            422, "CART_NOT_CONFIRMABLE", f"cart status is {cart_row['status']}"
        )
    if cart_row["proposal_hash"] != body.proposal_hash:
        raise CheckoutError(409, "CART_CHANGED", "cart has been re-priced since check")

    async with session.begin():
        existing_order = await repo.get_order_by_cart(session, cart_id)
    if existing_order is not None:
        return ConfirmCartResponse(
            order_id=str(existing_order["order_id"]),
            status=existing_order["status"],
            approve_url=existing_order["approve_url"] or "",
            total_minor=existing_order["total_minor"],
            currency=existing_order["currency"],
            expires_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

    order_id = str(uuid.uuid4())
    create_request_id = str(uuid.uuid4())
    # spec.md section 5 step 3: a random 128-bit `state` per binding (return, cancel),
    # stored as its SHA-256 only (repo.insert_return_binding) -- the raw value only ever
    # appears in the URL handed to PayPal/the browser, never persisted in the clear.
    return_state = secrets.token_hex(16)
    cancel_state = secrets.token_hex(16)
    binding_exp = datetime.now(UTC) + timedelta(
        seconds=settings.return_state_ttl_seconds
    )

    # R4: state written BEFORE the external paypal-adapter call, same transaction.
    async with session.begin():
        await repo.insert_order(
            session,
            order_id=order_id,
            cart_id=cart_id,
            buyer_id=buyer_id,
            mandate_id=cart_row["mandate_id"],
            status="CREATING",
            total_minor=cart_row["total_minor"],
            currency=cart_row["currency"],
            create_request_id=create_request_id,
            custom_id=str(cart_row["mandate_id"]),
            invoice_id=order_id,
        )
        await repo.insert_return_binding(
            session,
            state_hash=logic.sha256_hex(return_state.encode("utf-8")),
            order_id=order_id,
            buyer_id=buyer_id,
            mandate_id=str(cart_row["mandate_id"]),
            kind="return",
            exp=binding_exp,
        )
        await repo.insert_return_binding(
            session,
            state_hash=logic.sha256_hex(cancel_state.encode("utf-8")),
            order_id=order_id,
            buyer_id=buyer_id,
            mandate_id=str(cart_row["mandate_id"]),
            kind="cancel",
            exp=binding_exp,
        )

    token = mint_outbound_token(settings, "paypal-adapter")
    return_url = f"{settings.return_base_url}/checkout/return?state={return_state}"
    cancel_url = f"{settings.return_base_url}/checkout/cancel?state={cancel_state}"
    result = await clients.create_order(
        settings,
        token,
        idempotency_key=create_request_id,
        amount_minor=cart_row["total_minor"],
        currency=cart_row["currency"],
        custom_id=str(cart_row["mandate_id"]),
        invoice_id=order_id,
        return_url=return_url,
        cancel_url=cancel_url,
        ticket=create_request_id,  # placeholder until PS_CHECKOUT_TICKET_HMAC_KEY wiring lands
    )

    async with session.begin():
        order_row = await repo.get_order_row(session, order_id)
        assert order_row is not None
        if result.ok and result.body is not None:
            approve_url = result.body.get("approve_url", "")
            paypal_order_id = result.body.get("paypal_order_id", "")
            await repo.cas_order_status(
                session,
                order_id,
                order_row["version"],
                "AWAITING_APPROVAL",
                paypal_order_id=paypal_order_id,
                approve_url=approve_url,
            )
            if paypal_order_id:
                await repo.set_return_binding_paypal_order_id(
                    session, order_id, paypal_order_id
                )
            await repo.insert_outbox_event(
                session,
                event_type="order.created",
                aggregate_id=order_id,
                payload={
                    "order_id": order_id,
                    "mandate_id": str(cart_row["mandate_id"]),
                },
            )
            final_status = "AWAITING_APPROVAL"
        else:
            final_status = "CREATE_FAILED" if result.definite else "CREATE_UNKNOWN"
            await repo.cas_order_status(
                session,
                order_id,
                order_row["version"],
                final_status,
                failure_code=result.detail[:64],
            )
            approve_url = ""

        response_body = {
            "order_id": order_id,
            "status": final_status,
            "approve_url": approve_url,
            "total_minor": cart_row["total_minor"],
            "currency": cart_row["currency"],
            "expires_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        await repo.idempotency_store(
            session,
            buyer_id,
            "POST /carts/confirm",
            idempotency_key,
            repo.request_hash_of(body.model_dump()),
            201 if result.ok else 502,
            response_body,
        )

    if not result.ok:
        raise CheckoutError(
            502 if not result.definite else 422,
            final_status,
            f"order create did not succeed: {result.detail}",
            {"order_id": order_id},
        )

    return ConfirmCartResponse(**response_body)
