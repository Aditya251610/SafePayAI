"""GET /grants - mandate/spec.md section 9.3, api.md section 11."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app import mandate_logic, repo
from app.crypto import GRANT_HMAC_DOMAIN, canon_hash, verify_hmac
from app.deps import Principal, get_session, verify_internal_jwt
from app.errors import MandateError
from app.settings import get_bare_secrets, get_settings

router = APIRouter(tags=["grants"])


def _actor_id(principal: Principal) -> str:
    return principal.buyer_id or principal.sub


async def _grant_view(session: AsyncSession, grant_row: dict) -> dict:
    settings = get_settings()
    bare_secrets = get_bare_secrets()
    mandate_row = await repo.get_mandate_row(session, str(grant_row["mandate_id"]))
    spend_row = await repo.get_spend_row(session, str(grant_row["mandate_id"]))
    revocation_row = await repo.get_revocation_row(session, str(grant_row["mandate_id"]))

    grant_integrity_ok = _verify_grant_hmac(grant_row, settings, bare_secrets)
    mandate_integrity_ok = False
    mandate_status = "INVALID"
    if mandate_row is not None:
        mandate_integrity_ok, _ = repo.verify_integrity(mandate_row, spend_row, settings, bare_secrets)
        if mandate_integrity_ok:
            mandate_status = mandate_logic.derive_status(
                revoked=revocation_row is not None,
                expires_at=mandate_row["expires_at"],
                spent_minor=spend_row["spent_minor"],
                max_total_minor=mandate_row["max_total_minor"],
                now=repo.now_utc(),
            )

    integrity_ok = grant_integrity_ok and mandate_integrity_ok
    # protection_in_force (v1): true for any grant whose integrity re-verifies OK,
    # regardless of later mandate revoke/expire (D1 - earned protection stands).
    return {
        "grant_id": str(grant_row["grant_id"]),
        "mandate_id": str(grant_row["mandate_id"]),
        "order_id": str(grant_row["order_id"]),
        "capture_id": grant_row["capture_id"],
        "buyer_id": grant_row["buyer_id"],
        "mandate_hash": grant_row["mandate_hash"],
        "terms_hash": grant_row["terms_hash"],
        "terms": grant_row["terms"],
        "captured_amount_minor": grant_row["captured_amount_minor"],
        "captured_at": grant_row["captured_at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mandate_status": mandate_status,
        "protection_in_force": integrity_ok,
        "integrity": "OK" if integrity_ok else "FAILED",
    }


def _verify_grant_hmac(grant_row: dict, settings, bare_secrets) -> bool:
    terms_hash = canon_hash(
        {"mandate_id": str(grant_row["mandate_id"]), "mandate_hash": grant_row["mandate_hash"], "terms": grant_row["terms"]}
    )
    if terms_hash != grant_row["terms_hash"]:
        return False
    key = repo.key_bytes_for(grant_row["hmac_key_id"], settings, bare_secrets)
    if key is None:
        return False
    hash_bytes = bytes.fromhex(terms_hash)
    return verify_hmac(key, GRANT_HMAC_DOMAIN, hash_bytes, grant_row["buyer_id"], str(grant_row["order_id"]), grant_row["grant_hmac"])


@router.get("/grants")
async def list_grants(
    response: Response,
    order_id: str | None = None,
    principal: Principal = Depends(verify_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    if not order_id:
        raise MandateError(400, "VALIDATION_ERROR", "order_id is required", {"field": "order_id"})
    async with session.begin():
        grant_row = await repo.get_grant_by_order(session, order_id)
        if grant_row is None:
            raise MandateError(404, "GRANT_NOT_FOUND", "grant not found", {})
        if principal.role == "buyer" and grant_row["buyer_id"] != _actor_id(principal):
            raise MandateError(404, "GRANT_NOT_FOUND", "grant not found", {})
        return await _grant_view(session, grant_row)


@router.get("/grants/{grant_id}")
async def get_grant(
    grant_id: str,
    response: Response,
    principal: Principal = Depends(verify_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    async with session.begin():
        grant_row = await repo.get_grant_by_id(session, grant_id)
        if grant_row is None:
            raise MandateError(404, "GRANT_NOT_FOUND", "grant not found", {})
        if principal.role == "buyer" and grant_row["buyer_id"] != _actor_id(principal):
            raise MandateError(404, "GRANT_NOT_FOUND", "grant not found", {})
        return await _grant_view(session, grant_row)
