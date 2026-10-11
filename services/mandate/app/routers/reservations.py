"""Spend reservation endpoints (service callers only) - mandate/spec.md section 7, api.md section 10."""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app import mandate_logic, repo
from app.crypto import GRANT_HMAC_DOMAIN, canon_hash, compute_hmac
from app.deps import Principal, get_session, require_service_caller
from app.errors import MandateError
from app.schemas.reservations import (
    AuthorizeCaptureRequest,
    CommitRequest,
    MarkUnknownRequest,
    ReleaseRequest,
    ReservationCreateRequest,
)
from app.settings import get_bare_secrets, get_settings

router = APIRouter(tags=["reservations"])


def _reservation_view(row: dict, mandate_summary: dict | None = None) -> dict:
    out = {
        "reservation_id": str(row["reservation_id"]),
        "mandate_id": str(row["mandate_id"]),
        "order_id": str(row["order_id"]),
        "state": row["state"],
        "amount_minor": row["amount_minor"],
        "currency": row["currency"],
        "expires_at": row["expires_at"].strftime("%Y-%m-%dT%H:%M:%SZ")
        if row["expires_at"]
        else None,
        "authorized_at": row["authorized_at"].strftime("%Y-%m-%dT%H:%M:%SZ")
        if row["authorized_at"]
        else None,
        "captured_at": row["captured_at"].strftime("%Y-%m-%dT%H:%M:%SZ")
        if row["captured_at"]
        else None,
        "capture_id": row["capture_id"],
    }
    if mandate_summary is not None:
        out["mandate"] = mandate_summary
    return out


@router.post("/mandates/{mandate_id}/reservations", status_code=201)
async def create_reservation(
    mandate_id: str,
    body: ReservationCreateRequest,
    response: Response,
    principal: Principal = Depends(require_service_caller),
    session: AsyncSession = Depends(get_session),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    settings = get_settings()
    bare_secrets = get_bare_secrets()
    cart = body.cart.model_dump()
    mandate_logic.check_malformed_cart(cart)

    async with session.begin():
        existing = await repo.get_reservation_by_order(
            session, mandate_id, body.order_id
        )
        if existing is not None:
            if existing["amount_minor"] != body.amount_minor:
                raise MandateError(
                    409,
                    "RESERVATION_CONFLICT",
                    "reservation exists with a different amount",
                    {},
                )
            response.status_code = 200
            spend_row = await repo.get_spend_row(session, mandate_id)
            if spend_row is None:
                raise MandateError(
                    500,
                    "DATA_INCONSISTENCY",
                    "mandate referenced by reservation not found",
                    {},
                )
            remaining = (
                spend_row["max_total_minor"]
                - spend_row["spent_minor"]
                - spend_row["reserved_minor"]
            )
            return _reservation_view(
                existing,
                {
                    "spent_minor": spend_row["spent_minor"],
                    "reserved_minor": spend_row["reserved_minor"],
                    "remaining_minor": remaining,
                },
            )

        mandate_row = await repo.get_mandate_row(session, mandate_id)
        if mandate_row is None:
            raise MandateError(404, "MANDATE_NOT_FOUND", "mandate not found", {})

        spend_row = await repo.lock_spend_row(session, mandate_id, settings)
        revocation_row = await repo.get_revocation_row(session, mandate_id)
        integrity_ok, _failed_check = repo.verify_integrity(
            mandate_row, spend_row, settings, bare_secrets
        )
        now = repo.now_utc()
        status = mandate_logic.derive_status(
            revoked=revocation_row is not None,
            expires_at=mandate_row["expires_at"],
            spent_minor=spend_row["spent_minor"],
            max_total_minor=mandate_row["max_total_minor"],
            now=now,
        )
        remaining = (
            spend_row["max_total_minor"]
            - spend_row["spent_minor"]
            - spend_row["reserved_minor"]
        )
        eval_result = mandate_logic.evaluate_cart(
            integrity_ok=integrity_ok,
            status=status,
            merchant_allowlist=mandate_row["merchant_allowlist"],
            max_qty_per_line=mandate_row["max_qty_per_line"],
            currency=mandate_row["currency"],
            remaining_minor=remaining,
            cart=cart,
            expires_at=mandate_row["expires_at"],
            now=now,
            near_cap_percent=settings.advisory_near_cap_percent,
            expires_soon_seconds=settings.advisory_expires_soon_seconds,
        )
        if eval_result.decision != "ALLOW" or body.amount_minor > remaining:
            blocks = list(eval_result.hard_blocks)
            if body.amount_minor > remaining and not any(
                b["code"] == "OVER_CAP" for b in blocks
            ):
                blocks.append(
                    {
                        "code": "OVER_CAP",
                        "details": {
                            "total_minor": body.amount_minor,
                            "remaining_minor": remaining,
                        },
                    }
                )
            raise MandateError(
                409,
                "RESERVATION_REFUSED",
                "reservation refused",
                {"hard_blocks": blocks},
            )

        reservation_id = str(uuid.uuid4())
        expires_at = now + timedelta(seconds=settings.reservation_ttl_seconds)
        await repo.insert_reservation(
            session,
            reservation_id=reservation_id,
            mandate_id=mandate_id,
            order_id=body.order_id,
            amount_minor=body.amount_minor,
            currency=body.currency,
            proposal_hash=body.proposal_hash,
            expires_at=expires_at,
        )
        await repo.adjust_spend(session, mandate_id, reserved_delta=body.amount_minor)

        new_row = await repo.get_reservation_row(session, reservation_id)
        if new_row is None:
            raise MandateError(
                500,
                "DATA_INCONSISTENCY",
                "reservation vanished immediately after insert",
                {},
            )
        return _reservation_view(
            new_row,
            {
                "spent_minor": spend_row["spent_minor"],
                "reserved_minor": spend_row["reserved_minor"] + body.amount_minor,
                "remaining_minor": remaining - body.amount_minor,
            },
        )


@router.get("/reservations/{reservation_id}")
async def get_reservation(
    reservation_id: str,
    response: Response,
    principal: Principal = Depends(require_service_caller),
    session: AsyncSession = Depends(get_session),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    async with session.begin():
        row = await repo.get_reservation_row(session, reservation_id)
        if row is None:
            raise MandateError(
                404, "RESERVATION_NOT_FOUND", "reservation not found", {}
            )
        return _reservation_view(row)


async def _maybe_release_stale(
    session: AsyncSession, row: dict, settings: object
) -> dict:
    """Lazy TTL expiry for RESERVED (spec.md section 7.2 row: 'TTL expiry'). Not yet wired into
    any route (flagged out of this wave's scope) - kept type-correct so it doesn't silently
    bitrot into a None-return bug before it is."""
    if row["state"] != "RESERVED" or row["expires_at"] is None:
        return row
    if repo.now_utc() < row["expires_at"]:
        return row
    await repo.set_reservation_state(
        session, str(row["reservation_id"]), "RELEASED", release_reason="TTL_EXPIRED"
    )
    await repo.adjust_spend(
        session, str(row["mandate_id"]), reserved_delta=-row["amount_minor"]
    )
    refreshed = await repo.get_reservation_row(session, str(row["reservation_id"]))
    if refreshed is None:
        raise MandateError(
            500, "DATA_INCONSISTENCY", "reservation vanished during TTL release", {}
        )
    return refreshed


@router.post("/reservations/{reservation_id}/authorize-capture")
async def authorize_capture(
    reservation_id: str,
    body: AuthorizeCaptureRequest,
    response: Response,
    principal: Principal = Depends(require_service_caller),
    session: AsyncSession = Depends(get_session),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    settings = get_settings()
    bare_secrets = get_bare_secrets()
    async with session.begin():
        row = await repo.get_reservation_row(session, reservation_id)
        if row is None:
            raise MandateError(
                404, "RESERVATION_NOT_FOUND", "reservation not found", {}
            )
        mandate_row = await repo.get_mandate_row(session, str(row["mandate_id"]))
        if mandate_row is None:
            raise MandateError(
                500,
                "DATA_INCONSISTENCY",
                "mandate referenced by reservation not found",
                {},
            )

        if row["state"] == "CAPTURING":
            return {
                "reservation_id": reservation_id,
                "state": "CAPTURING",
                "authorized_at": row["authorized_at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        if row["state"] in ("CAPTURED", "RELEASED", "CAPTURE_UNKNOWN"):
            raise MandateError(
                409,
                "INVALID_RESERVATION_STATE",
                "reservation is not in a state that can be authorized",
                {},
            )
        if row["state"] != "RESERVED":
            raise MandateError(
                409, "INVALID_RESERVATION_STATE", "unexpected reservation state", {}
            )
        if (
            str(row["order_id"]) != body.order_id
            or row["amount_minor"] != body.amount_minor
        ):
            raise MandateError(
                409,
                "AMOUNT_MISMATCH",
                "order_id/amount_minor do not match the reservation",
                {},
            )

        spend_row = await repo.lock_spend_row(session, str(row["mandate_id"]), settings)
        revocation_row = await repo.get_revocation_row(session, str(row["mandate_id"]))
        integrity_ok, _failed_check = repo.verify_integrity(
            mandate_row, spend_row, settings, bare_secrets
        )
        now = repo.now_utc()
        status = mandate_logic.derive_status(
            revoked=revocation_row is not None,
            expires_at=mandate_row["expires_at"],
            spent_minor=spend_row["spent_minor"],
            max_total_minor=mandate_row["max_total_minor"],
            now=now,
        )

        refusal_code = None
        if not integrity_ok:
            refusal_code = "MANDATE_INTEGRITY_FAILED"
        elif status == "revoked":
            refusal_code = "MANDATE_REVOKED"
        elif status == "expired":
            refusal_code = "MANDATE_EXPIRED"
        elif row["expires_at"] is not None and now >= row["expires_at"]:
            refusal_code = "RESERVATION_EXPIRED"

        if refusal_code is not None:
            await repo.set_reservation_state(
                session, reservation_id, "RELEASED", release_reason=refusal_code
            )
            await repo.adjust_spend(
                session, str(row["mandate_id"]), reserved_delta=-row["amount_minor"]
            )
            raise MandateError(409, refusal_code, "authorize-capture refused", {})

        # Point of no return.
        await repo.set_reservation_state(
            session, reservation_id, "CAPTURING", authorized_at=now
        )
        return {
            "reservation_id": reservation_id,
            "state": "CAPTURING",
            "authorized_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }


@router.post("/reservations/{reservation_id}/mark-unknown")
async def mark_unknown(
    reservation_id: str,
    body: MarkUnknownRequest,
    response: Response,
    principal: Principal = Depends(require_service_caller),
    session: AsyncSession = Depends(get_session),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    async with session.begin():
        row = await repo.get_reservation_row(session, reservation_id)
        if row is None:
            raise MandateError(
                404, "RESERVATION_NOT_FOUND", "reservation not found", {}
            )
        if row["state"] == "CAPTURE_UNKNOWN":
            return {"reservation_id": reservation_id, "state": "CAPTURE_UNKNOWN"}
        if row["state"] != "CAPTURING":
            raise MandateError(
                409, "INVALID_RESERVATION_STATE", "reservation is not CAPTURING", {}
            )
        await repo.set_reservation_state(
            session, reservation_id, "CAPTURE_UNKNOWN", release_reason=body.reason_code
        )
        return {"reservation_id": reservation_id, "state": "CAPTURE_UNKNOWN"}


@router.post("/reservations/{reservation_id}/commit")
async def commit_reservation(
    reservation_id: str,
    body: CommitRequest,
    response: Response,
    principal: Principal = Depends(require_service_caller),
    session: AsyncSession = Depends(get_session),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    settings = get_settings()
    bare_secrets = get_bare_secrets()
    async with session.begin():
        row = await repo.get_reservation_row(session, reservation_id)
        if row is None:
            raise MandateError(
                404, "RESERVATION_NOT_FOUND", "reservation not found", {}
            )

        if row["state"] == "CAPTURED":
            existing_grant = await repo.get_grant_by_order(
                session, str(row["order_id"])
            )
            spend_row = await repo.get_spend_row(session, str(row["mandate_id"]))
            if spend_row is None:
                raise MandateError(
                    500,
                    "DATA_INCONSISTENCY",
                    "mandate referenced by reservation not found",
                    {},
                )
            remaining = (
                spend_row["max_total_minor"]
                - spend_row["spent_minor"]
                - spend_row["reserved_minor"]
            )
            return {
                "reservation_id": reservation_id,
                "state": "CAPTURED",
                "grant_id": str(existing_grant["grant_id"]) if existing_grant else None,
                "mandate": {
                    "spent_minor": spend_row["spent_minor"],
                    "reserved_minor": spend_row["reserved_minor"],
                    "remaining_minor": remaining,
                },
            }
        if row["state"] not in ("CAPTURING", "CAPTURE_UNKNOWN"):
            raise MandateError(
                409, "INVALID_RESERVATION_STATE", "reservation is not capturable", {}
            )
        if body.captured_amount_minor != row["amount_minor"]:
            raise MandateError(
                409,
                "AMOUNT_MISMATCH",
                "captured amount does not match the reservation",
                {},
            )

        mandate_row = await repo.get_mandate_row(session, str(row["mandate_id"]))
        if mandate_row is None:
            raise MandateError(
                500,
                "DATA_INCONSISTENCY",
                "mandate referenced by reservation not found",
                {},
            )
        spend_row = await repo.lock_spend_row(session, str(row["mandate_id"]), settings)
        captured_at_dt = mandate_logic.parse_utc_timestamp(
            body.captured_at, "captured_at"
        )

        # D1 / spec.md section 8: commit is allowed even if the mandate is now
        # revoked/expired - authorize-capture was the last point where "stop" could win.
        await repo.set_reservation_state(
            session,
            reservation_id,
            "CAPTURED",
            captured_at=captured_at_dt,
            capture_id=body.capture_id,
        )
        await repo.adjust_spend(
            session,
            str(row["mandate_id"]),
            spent_delta=row["amount_minor"],
            reserved_delta=-row["amount_minor"],
        )

        protection = mandate_row["protection"]
        terms_for_grant = {
            "kinds_covered": protection["kinds_covered"],
            "max_refund_minor": protection["max_refund_minor"],
            "deliver_by_days": protection["deliver_by_days"],
            "currency": mandate_row["currency"],
            "revoke_effect": mandate_row["revoke_effect"],
            "policy_version": mandate_row["policy_version"],
        }
        grant_id = str(uuid.uuid4())
        terms_hash = canon_hash(
            {
                "mandate_id": str(row["mandate_id"]),
                "mandate_hash": mandate_row["mandate_hash"],
                "terms": terms_for_grant,
            }
        )
        key_id = settings.hmac_key_id
        key = repo.key_bytes_for(key_id, settings, bare_secrets)
        if key is None:
            raise MandateError(
                500,
                "HMAC_KEY_UNAVAILABLE",
                "configured hmac_key_id has no usable secret",
                {},
            )
        grant_hash_bytes = bytes.fromhex(terms_hash)
        grant_hmac = compute_hmac(
            key,
            GRANT_HMAC_DOMAIN,
            grant_hash_bytes,
            mandate_row["buyer_id"],
            str(row["order_id"]),
        )

        await repo.insert_grant(
            session,
            grant_id=grant_id,
            mandate_id=str(row["mandate_id"]),
            order_id=str(row["order_id"]),
            capture_id=body.capture_id,
            buyer_id=mandate_row["buyer_id"],
            mandate_hash=mandate_row["mandate_hash"],
            terms=terms_for_grant,
            terms_hash=terms_hash,
            captured_amount_minor=body.captured_amount_minor,
            captured_at=captured_at_dt,
            grant_hmac=grant_hmac,
            hmac_key_id=key_id,
        )

        spend_event_id = repo.deterministic_event_id(
            str(row["mandate_id"]), "mandate.spend_committed", str(reservation_id)
        )
        await repo.insert_outbox_event(
            session,
            event_type="mandate.spend_committed",
            mandate_id=str(row["mandate_id"]),
            event_id=spend_event_id,
            payload={
                "mandate_id": str(row["mandate_id"]),
                "order_id": str(row["order_id"]),
                "reservation_id": reservation_id,
                "capture_id": body.capture_id,
                "amount_minor": row["amount_minor"],
                "spent_minor_after": spend_row["spent_minor"] + row["amount_minor"],
                "remaining_minor_after": spend_row["max_total_minor"]
                - (spend_row["spent_minor"] + row["amount_minor"]),
            },
        )
        grant_event_id = repo.deterministic_event_id(
            str(row["mandate_id"]), "mandate.protection_granted", grant_id
        )
        await repo.insert_outbox_event(
            session,
            event_type="mandate.protection_granted",
            mandate_id=str(row["mandate_id"]),
            event_id=grant_event_id,
            payload={
                "grant_id": grant_id,
                "mandate_id": str(row["mandate_id"]),
                "order_id": str(row["order_id"]),
                "capture_id": body.capture_id,
                "terms_hash": terms_hash,
                "mandate_hash": mandate_row["mandate_hash"],
            },
        )

        remaining = (
            spend_row["max_total_minor"]
            - (spend_row["spent_minor"] + row["amount_minor"])
            - (spend_row["reserved_minor"] - row["amount_minor"])
        )
        return {
            "reservation_id": reservation_id,
            "state": "CAPTURED",
            "grant_id": grant_id,
            "mandate": {
                "spent_minor": spend_row["spent_minor"] + row["amount_minor"],
                "reserved_minor": spend_row["reserved_minor"] - row["amount_minor"],
                "remaining_minor": remaining,
            },
            "protection": {
                "kinds_covered": protection["kinds_covered"],
                "max_refund_minor": protection["max_refund_minor"],
                "deliver_by_days": protection["deliver_by_days"],
                "terms_hash": terms_hash,
            },
        }


@router.post("/reservations/{reservation_id}/release")
async def release_reservation(
    reservation_id: str,
    body: ReleaseRequest,
    response: Response,
    principal: Principal = Depends(require_service_caller),
    session: AsyncSession = Depends(get_session),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    async with session.begin():
        row = await repo.get_reservation_row(session, reservation_id)
        if row is None:
            raise MandateError(
                404, "RESERVATION_NOT_FOUND", "reservation not found", {}
            )
        if row["state"] == "RELEASED":
            return {"state": "RELEASED"}
        if row["state"] == "CAPTURED":
            raise MandateError(
                409, "INVALID_RESERVATION_STATE", "reservation already captured", {}
            )
        if (
            row["state"] in ("CAPTURING", "CAPTURE_UNKNOWN")
            and body.capture_outcome != "NOT_CAPTURED"
        ):
            raise MandateError(
                409,
                "INVALID_RESERVATION_STATE",
                "capture_outcome=NOT_CAPTURED required to release this state",
                {},
            )

        await repo.set_reservation_state(
            session, reservation_id, "RELEASED", release_reason=body.reason_code
        )
        await repo.adjust_spend(
            session, str(row["mandate_id"]), reserved_delta=-row["amount_minor"]
        )
        return {"state": "RELEASED"}
