"""Mandate lifecycle endpoints - real logic per mandate/spec.md and api.md sections 4-9."""

from __future__ import annotations

import base64
import secrets
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import mandate_logic, repo
from app.crypto import (
    MANDATE_HMAC_DOMAIN,
    canonical_json_bytes,
    compute_hmac,
    sha256_hex,
)
from app.deps import (
    Principal,
    get_session,
    require_buyer,
    require_service_caller,
    verify_internal_jwt,
)
from app.errors import MandateError
from app.schemas.reservations import EvaluateRequest
from app.schemas.terms import MandatePreviewRequest, MandateSignRequest, RevokeRequest
from app.settings import get_bare_secrets, get_settings

router = APIRouter(tags=["mandates"])


def _actor_id(principal: Principal) -> str:
    return principal.buyer_id or principal.sub


def _remaining(max_total: int, spent: int, reserved: int) -> int:
    return max_total - spent - reserved


def _owner_view(
    mandate_row: dict, spend_row: dict, status: str, revocation_row: dict | None
) -> dict:
    body = {
        "mandate_id": str(mandate_row["mandate_id"]),
        "buyer_id": mandate_row["buyer_id"],
        "status": status,
        "integrity": "OK",
        "schema": mandate_row["schema"],
        "render_version": mandate_row["render_version"],
        "policy_version": mandate_row["policy_version"],
        "currency": mandate_row["currency"],
        "max_total_minor": mandate_row["max_total_minor"],
        "max_qty_per_line": mandate_row["max_qty_per_line"],
        "merchant_allowlist": mandate_row["merchant_allowlist"],
        "intent_text": mandate_row["intent_text"],
        "expires_at": mandate_row["expires_at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
        "protection": mandate_row["protection"],
        "revoke_effect": mandate_row["revoke_effect"],
        "mandate_hash": mandate_row["mandate_hash"],
        "screen_text_hash": mandate_row["screen_text_hash"],
        "hmac_key_id": mandate_row["hmac_key_id"],
        "spent_minor": spend_row["spent_minor"],
        "reserved_minor": spend_row["reserved_minor"],
        "remaining_minor": _remaining(
            spend_row["max_total_minor"],
            spend_row["spent_minor"],
            spend_row["reserved_minor"],
        ),
        "created_at": mandate_row["created_at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if revocation_row:
        body["revoked_at"] = revocation_row["revoked_at"].strftime("%Y-%m-%dT%H:%M:%SZ")
    return body


def _merchant_view(mandate_row: dict, status: str) -> dict:
    return {
        "mandate_id": str(mandate_row["mandate_id"]),
        "status": status,
        "currency": mandate_row["currency"],
        "expires_at": mandate_row["expires_at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
        "protection": mandate_row["protection"],
        "merchant_ids": [m["merchant_id"] for m in mandate_row["merchant_allowlist"]],
    }


def _invalid_view(mandate_row: dict) -> dict:
    return {
        "mandate_id": str(mandate_row["mandate_id"]),
        "status": "INVALID",
        "integrity": "FAILED",
        "mandate_hash": mandate_row["mandate_hash"],
        "screen_text_hash": mandate_row["screen_text_hash"],
        "hmac_key_id": mandate_row["hmac_key_id"],
    }


async def _emit_expired_if_needed(
    session: AsyncSession, mandate_row: dict, status: str
) -> None:
    if status != "expired":
        return
    event_id = repo.deterministic_event_id(
        str(mandate_row["mandate_id"]), "mandate.expired"
    )
    await repo.insert_outbox_event(
        session,
        event_type="mandate.expired",
        mandate_id=str(mandate_row["mandate_id"]),
        payload={
            "mandate_id": str(mandate_row["mandate_id"]),
            "mandate_hash": mandate_row["mandate_hash"],
            "expired_at": mandate_row["expires_at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        event_id=event_id,
    )


async def _emit_integrity_failed_if_needed(
    session: AsyncSession, mandate_id: str, check: str | None, key_id: str
) -> None:
    # `check` is None only if verify_integrity's own invariant (failed_check is set whenever
    # integrity_ok is False) is ever violated - record that distinctly rather than crash.
    event_id = repo.deterministic_event_id(mandate_id, "mandate.integrity_failed")
    await repo.insert_outbox_event(
        session,
        event_type="mandate.integrity_failed",
        mandate_id=mandate_id,
        payload={
            "mandate_id": mandate_id,
            "check": check or "UNKNOWN_FAILED_CHECK",
            "key_id": key_id,
        },
        event_id=event_id,
    )


@router.post("/mandates/preview")
async def preview_mandate(
    body: MandatePreviewRequest,
    response: Response,
    principal: Principal = Depends(require_buyer),
    session: AsyncSession = Depends(get_session),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    settings = get_settings()
    now = repo.now_utc()
    normalized = mandate_logic.normalize_terms(body.terms, settings, now=now)
    screen_text = mandate_logic.render_text(normalized)
    text_hash = mandate_logic.screen_text_hash(screen_text)
    digest_input = dict(normalized)
    digest_input["screen_text_hash"] = text_hash
    digest = mandate_logic.terms_digest(digest_input)

    raw_nonce = (
        base64.urlsafe_b64encode(secrets.token_bytes(16)).decode("ascii").rstrip("=")
    )
    nonce_hash = sha256_hex(raw_nonce.encode("ascii"))
    buyer_id = _actor_id(principal)

    async with session.begin():
        await repo.insert_nonce(
            session,
            nonce_hash,
            buyer_id,
            "mandate_sign",
            digest,
            settings.nonce_ttl_seconds,
        )

    nonce_expires_at = now + timedelta(seconds=settings.nonce_ttl_seconds)
    return {
        "normalized_terms": normalized,
        "screen_text": screen_text,
        "screen_text_hash": text_hash,
        "render_version": mandate_logic.RENDER_VERSION,
        "policy_version": settings.policy_version,
        "nonce": raw_nonce,
        "nonce_expires_at": nonce_expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@router.post("/mandates", status_code=201)
async def sign_mandate(
    body: MandateSignRequest,
    response: Response,
    principal: Principal = Depends(require_buyer),
    session: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    settings = get_settings()
    bare_secrets = get_bare_secrets()
    if not settings.signing_enabled:
        raise MandateError(503, "SIGNING_DISABLED", "signing is currently disabled", {})
    if not idempotency_key:
        raise MandateError(
            400,
            "VALIDATION_ERROR",
            "Idempotency-Key header is required",
            {"field": "Idempotency-Key"},
        )

    buyer_id = _actor_id(principal)
    scope = f"{buyer_id}|POST /mandates"
    request_hash = repo.request_hash_of(
        {
            "terms": body.terms.model_dump(),
            "screen_text_hash": body.screen_text_hash,
            "nonce": body.nonce,
        }
    )

    now = repo.now_utc()
    normalized = mandate_logic.normalize_terms(body.terms, settings, now=now)
    screen_text = mandate_logic.render_text(normalized)
    text_hash = mandate_logic.screen_text_hash(screen_text)
    if text_hash != body.screen_text_hash:
        raise MandateError(
            422,
            "SCREEN_TEXT_MISMATCH",
            "screen text hash does not match re-rendered terms",
            {},
        )

    digest_input = dict(normalized)
    digest_input["screen_text_hash"] = text_hash
    digest = mandate_logic.terms_digest(digest_input)
    nonce_hash = sha256_hex(body.nonce.encode("ascii"))

    async with session.begin():
        existing = await repo.idempotency_lookup(session, scope, idempotency_key)
        if existing is not None:
            if existing["request_hash"] != request_hash:
                raise MandateError(
                    409,
                    "IDEMPOTENCY_KEY_REUSED",
                    "idempotency key reused with a different request",
                    {},
                )
            response.headers["Idempotent-Replay"] = "true"
            cached_response: dict = existing["response"]
            return cached_response

        await repo.check_nonce_valid(
            session, nonce_hash, buyer_id, "mandate_sign", digest
        )

        mandate_id = str(uuid.uuid4())
        created_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        canonical_obj = mandate_logic.build_mandate_canonical_object(
            mandate_id=mandate_id,
            buyer_id=buyer_id,
            normalized=normalized,
            nonce=body.nonce,
            created_at=created_at,
            screen_text_hash_value=text_hash,
        )
        canonical_bytes = canonical_json_bytes(canonical_obj)
        canonical_text = canonical_bytes.decode("utf-8")
        mandate_hash = sha256_hex(canonical_bytes)
        key_id = settings.hmac_key_id
        key = repo.key_bytes_for(key_id, settings, bare_secrets)
        if key is None:
            raise MandateError(503, "NOT_READY", "signing key unavailable", {})
        hmac_hex = compute_hmac(
            key, MANDATE_HMAC_DOMAIN, bytes.fromhex(mandate_hash), buyer_id, body.nonce
        )

        try:
            await session.execute(
                text(
                    """
                INSERT INTO mandate.mandates
                    (mandate_id, buyer_id, schema, currency, max_total_minor, max_qty_per_line,
                     merchant_allowlist, intent_text, expires_at, protection, revoke_effect,
                     policy_version, nonce, render_version, screen_text_hash, canonical_json,
                     mandate_hash, hmac, hmac_alg, hmac_key_id, signed_at, created_at)
                VALUES
                    (:mandate_id, :buyer_id, :schema, :currency, :max_total_minor, :max_qty_per_line,
                     :merchant_allowlist, :intent_text, :expires_at, :protection, :revoke_effect,
                     :policy_version, :nonce, :render_version, :screen_text_hash, :canonical_json,
                     :mandate_hash, :hmac, 'HMAC-SHA256', :hmac_key_id, :signed_at, :created_at)
                """
                ),
                {
                    "mandate_id": mandate_id,
                    "buyer_id": buyer_id,
                    "schema": mandate_logic.SCHEMA_VERSION,
                    "currency": normalized["currency"],
                    "max_total_minor": normalized["max_total_minor"],
                    "max_qty_per_line": normalized["max_qty_per_line"],
                    "merchant_allowlist": repo.to_jsonb_text(
                        normalized["merchant_allowlist"]
                    ),
                    "intent_text": normalized["intent_text"],
                    "expires_at": mandate_logic.parse_utc_timestamp(
                        normalized["expires_at"], "expires_at"
                    ),
                    "protection": repo.to_jsonb_text(normalized["protection"]),
                    "revoke_effect": normalized["revoke_effect"],
                    "policy_version": normalized["policy_version"],
                    "nonce": body.nonce,
                    "render_version": mandate_logic.RENDER_VERSION,
                    "screen_text_hash": text_hash,
                    "canonical_json": canonical_text,
                    "mandate_hash": mandate_hash,
                    "hmac": hmac_hex,
                    "hmac_key_id": key_id,
                    "signed_at": now,
                    "created_at": now,
                },
            )
        except IntegrityError as exc:
            # The only UNIQUE constraint on mandates besides the mandate_id PK is
            # UNIQUE(nonce) - mandate_id is a fresh uuid4, so any IntegrityError here
            # means the nonce was already burnt by a concurrent/earlier sign.
            raise MandateError(409, "NONCE_INVALID", "nonce already used", {}) from exc

        await session.execute(
            text(
                "INSERT INTO mandate.mandate_spend (mandate_id, max_total_minor) VALUES (:id, :max_total_minor)"
            ),
            {"id": mandate_id, "max_total_minor": normalized["max_total_minor"]},
        )
        await repo.consume_nonce(session, nonce_hash, mandate_id)

        intent_text_hash = sha256_hex(normalized["intent_text"].encode("utf-8"))
        signed_event_id = repo.deterministic_event_id(mandate_id, "mandate.signed")
        await repo.insert_outbox_event(
            session,
            event_type="mandate.signed",
            mandate_id=mandate_id,
            event_id=signed_event_id,
            payload={
                "mandate_id": mandate_id,
                "buyer_id": buyer_id,
                "mandate_hash": mandate_hash,
                "screen_text_hash": text_hash,
                "render_version": mandate_logic.RENDER_VERSION,
                "policy_version": normalized["policy_version"],
                "nonce": body.nonce,
                "max_total_minor": normalized["max_total_minor"],
                "currency": normalized["currency"],
                "merchant_ids": [
                    m["merchant_id"] for m in normalized["merchant_allowlist"]
                ],
                "expires_at": normalized["expires_at"],
                "protection": normalized["protection"],
                "revoke_effect": normalized["revoke_effect"],
                "hmac_key_id": key_id,
                "intent_text_hash": intent_text_hash,
            },
        )

        response_body = {
            "mandate_id": mandate_id,
            "buyer_id": buyer_id,
            "status": "active",
            "integrity": "OK",
            "schema": mandate_logic.SCHEMA_VERSION,
            "render_version": mandate_logic.RENDER_VERSION,
            "policy_version": normalized["policy_version"],
            "currency": normalized["currency"],
            "max_total_minor": normalized["max_total_minor"],
            "max_qty_per_line": normalized["max_qty_per_line"],
            "merchant_allowlist": normalized["merchant_allowlist"],
            "intent_text": normalized["intent_text"],
            "expires_at": normalized["expires_at"],
            "protection": normalized["protection"],
            "revoke_effect": normalized["revoke_effect"],
            "mandate_hash": mandate_hash,
            "screen_text_hash": text_hash,
            "hmac_key_id": key_id,
            "spent_minor": 0,
            "reserved_minor": 0,
            "remaining_minor": normalized["max_total_minor"],
            "created_at": created_at,
        }
        await repo.idempotency_store(
            session, scope, idempotency_key, request_hash, response_body
        )

    return response_body


@router.get("/mandates")
async def list_mandates(
    response: Response,
    limit: int = 20,
    principal: Principal = Depends(require_buyer),
    session: AsyncSession = Depends(get_session),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    buyer_id = _actor_id(principal)
    limit = max(1, min(limit, 100))
    async with session.begin():
        result = await session.execute(
            text(
                f"SELECT {repo.MANDATE_COLUMNS} FROM mandate.mandates WHERE buyer_id = :buyer_id "
                "ORDER BY created_at DESC LIMIT :limit"
            ),
            {"buyer_id": buyer_id, "limit": limit},
        )
        rows = [dict(r) for r in result.mappings().all()]
        items = []
        for row in rows:
            spend_row = await repo.get_spend_row(session, str(row["mandate_id"]))
            if spend_row is None:
                raise MandateError(
                    500, "DATA_INCONSISTENCY", "mandate has no spend row", {}
                )
            revocation_row = await repo.get_revocation_row(
                session, str(row["mandate_id"])
            )
            status = mandate_logic.derive_status(
                revoked=revocation_row is not None,
                expires_at=row["expires_at"],
                spent_minor=spend_row["spent_minor"],
                max_total_minor=row["max_total_minor"],
                now=repo.now_utc(),
            )
            items.append(_owner_view(row, spend_row, status, revocation_row))
    return {"items": items}


async def _load_mandate_context(
    session: AsyncSession, mandate_id: str
) -> tuple[dict, dict, dict | None]:
    mandate_row = await repo.get_mandate_row(session, mandate_id)
    if mandate_row is None:
        raise MandateError(404, "MANDATE_NOT_FOUND", "mandate not found", {})
    spend_row = await repo.get_spend_row(session, mandate_id)
    if spend_row is None:
        raise MandateError(500, "DATA_INCONSISTENCY", "mandate has no spend row", {})
    revocation_row = await repo.get_revocation_row(session, mandate_id)
    return mandate_row, spend_row, revocation_row


@router.get("/mandates/{mandate_id}")
async def get_mandate(
    mandate_id: str,
    response: Response,
    principal: Principal = Depends(verify_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    settings = get_settings()
    bare_secrets = get_bare_secrets()
    async with session.begin():
        mandate_row, spend_row, revocation_row = await _load_mandate_context(
            session, mandate_id
        )
        is_owner = principal.role == "buyer" and mandate_row["buyer_id"] == _actor_id(
            principal
        )
        if principal.role == "buyer" and not is_owner:
            raise MandateError(404, "MANDATE_NOT_FOUND", "mandate not found", {})

        integrity_ok, failed_check = repo.verify_integrity(
            mandate_row, spend_row, settings, bare_secrets
        )
        if not integrity_ok:
            await _emit_integrity_failed_if_needed(
                session, mandate_id, failed_check, mandate_row["hmac_key_id"]
            )
            return _invalid_view(mandate_row)

        status = mandate_logic.derive_status(
            revoked=revocation_row is not None,
            expires_at=mandate_row["expires_at"],
            spent_minor=spend_row["spent_minor"],
            max_total_minor=mandate_row["max_total_minor"],
            now=repo.now_utc(),
        )
        await _emit_expired_if_needed(session, mandate_row, status)

        if principal.role == "merchant":
            return _merchant_view(mandate_row, status)
        if is_owner or principal.role == "reviewer" or principal.sub.startswith("svc:"):
            return _owner_view(mandate_row, spend_row, status, revocation_row)
        raise MandateError(403, "ROLE_NOT_ALLOWED", "role not allowed", {})


@router.get("/mandates/{mandate_id}/terms")
async def get_mandate_terms(
    mandate_id: str,
    response: Response,
    principal: Principal = Depends(verify_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    settings = get_settings()
    bare_secrets = get_bare_secrets()
    async with session.begin():
        mandate_row, spend_row, revocation_row = await _load_mandate_context(
            session, mandate_id
        )
        if principal.role == "buyer" and mandate_row["buyer_id"] != _actor_id(
            principal
        ):
            raise MandateError(404, "MANDATE_NOT_FOUND", "mandate not found", {})

        integrity_ok, failed_check = repo.verify_integrity(
            mandate_row, spend_row, settings, bare_secrets
        )
        if not integrity_ok:
            await _emit_integrity_failed_if_needed(
                session, mandate_id, failed_check, mandate_row["hmac_key_id"]
            )
            integrity_label = "FAILED"
        else:
            integrity_label = "OK"

        status = mandate_logic.derive_status(
            revoked=revocation_row is not None,
            expires_at=mandate_row["expires_at"],
            spent_minor=spend_row["spent_minor"],
            max_total_minor=mandate_row["max_total_minor"],
            now=repo.now_utc(),
        )
        await _emit_expired_if_needed(session, mandate_row, status)

        terms_obj = {
            "kinds_covered": mandate_row["protection"]["kinds_covered"],
            "max_refund_minor": mandate_row["protection"]["max_refund_minor"],
            "deliver_by_days": mandate_row["protection"]["deliver_by_days"],
        }
        terms_hash = sha256_hex(
            canonical_json_bytes(
                {
                    "mandate_id": mandate_id,
                    "mandate_hash": mandate_row["mandate_hash"],
                    "terms": terms_obj,
                }
            )
        )
        return {
            "mandate_id": mandate_id,
            "mandate_hash": mandate_row["mandate_hash"],
            "terms_hash": terms_hash,
            "mandate_status": status,
            "integrity": integrity_label,
            "protection": mandate_row["protection"],
            "revoke_effect": mandate_row["revoke_effect"],
            "policy_version": mandate_row["policy_version"],
            "currency": mandate_row["currency"],
        }


@router.get("/mandates/{mandate_id}/summary")
async def get_mandate_summary(
    mandate_id: str,
    response: Response,
    principal: Principal = Depends(require_service_caller),
    session: AsyncSession = Depends(get_session),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    settings = get_settings()
    bare_secrets = get_bare_secrets()
    async with session.begin():
        mandate_row, spend_row, revocation_row = await _load_mandate_context(
            session, mandate_id
        )
        integrity_ok, failed_check = repo.verify_integrity(
            mandate_row, spend_row, settings, bare_secrets
        )
        if not integrity_ok:
            await _emit_integrity_failed_if_needed(
                session, mandate_id, failed_check, mandate_row["hmac_key_id"]
            )
            return _invalid_view(mandate_row)
        status = mandate_logic.derive_status(
            revoked=revocation_row is not None,
            expires_at=mandate_row["expires_at"],
            spent_minor=spend_row["spent_minor"],
            max_total_minor=mandate_row["max_total_minor"],
            now=repo.now_utc(),
        )
        await _emit_expired_if_needed(session, mandate_row, status)
        return {
            "mandate_id": mandate_id,
            "status": status,
            "currency": mandate_row["currency"],
            "merchant_ids": [
                m["merchant_id"] for m in mandate_row["merchant_allowlist"]
            ],
            "max_qty_per_line": mandate_row["max_qty_per_line"],
            "remaining_minor": _remaining(
                spend_row["max_total_minor"],
                spend_row["spent_minor"],
                spend_row["reserved_minor"],
            ),
            "spent_minor": spend_row["spent_minor"],
            "reserved_minor": spend_row["reserved_minor"],
            "expires_at": mandate_row["expires_at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
            "policy_version": mandate_row["policy_version"],
        }


@router.get("/mandates/{mandate_id}/verify")
async def verify_mandate(
    mandate_id: str,
    response: Response,
    principal: Principal = Depends(verify_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    settings = get_settings()
    bare_secrets = get_bare_secrets()
    async with session.begin():
        mandate_row, spend_row, _revocation_row = await _load_mandate_context(
            session, mandate_id
        )
        if principal.role == "buyer" and mandate_row["buyer_id"] != _actor_id(
            principal
        ):
            raise MandateError(404, "MANDATE_NOT_FOUND", "mandate not found", {})
        if principal.role not in ("buyer", "reviewer") and not principal.sub.startswith(
            "svc:"
        ):
            raise MandateError(403, "ROLE_NOT_ALLOWED", "role not allowed", {})

        result = repo.verify_integrity_detailed(
            mandate_row, spend_row, settings, bare_secrets
        )
        if not result.ok:
            await _emit_integrity_failed_if_needed(
                session, mandate_id, result.failed_check, mandate_row["hmac_key_id"]
            )
        return {
            "mandate_id": mandate_id,
            "integrity": "OK" if result.ok else "FAILED",
            "checks": result.as_dict(),
            "mandate_hash": mandate_row["mandate_hash"],
            "screen_text_hash": mandate_row["screen_text_hash"],
            "hmac_key_id": mandate_row["hmac_key_id"],
            "audit_compare_hint": "compare mandate_hash with the mandate.signed entry in the audit chain",
        }


@router.post("/mandates/{mandate_id}/revoke")
async def revoke_mandate(
    mandate_id: str,
    body: RevokeRequest,
    response: Response,
    principal: Principal = Depends(require_buyer),
    session: AsyncSession = Depends(get_session),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    settings = get_settings()
    async with session.begin():
        mandate_row = await repo.get_mandate_row(session, mandate_id)
        if mandate_row is None or mandate_row["buyer_id"] != _actor_id(principal):
            raise MandateError(404, "MANDATE_NOT_FOUND", "mandate not found", {})

        await repo.lock_spend_row(session, mandate_id, settings)
        revocation_row = await repo.get_revocation_row(session, mandate_id)
        now = repo.now_utc()

        if revocation_row is not None:
            # Idempotent replay: return the original revocation body, no second event.
            released = await session.execute(
                text(
                    "SELECT count(*) FROM mandate.spend_reservations WHERE mandate_id = :id AND release_reason = 'MANDATE_REVOKED'"
                ),
                {"id": mandate_id},
            )
            released_count = released.scalar() or 0
            return {
                "mandate_id": mandate_id,
                "status": "revoked",
                "revoked_at": revocation_row["revoked_at"].strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "released_reservations": released_count,
                "revoke_effect": mandate_row["revoke_effect"],
                "earned_protection_unchanged": True,
                "message_code": "FUTURE_PURCHASES_STOPPED",
            }

        if now >= mandate_row["expires_at"]:
            # spec Q4: already-expired mandate -> 200 no-op, no event.
            return {"status": "expired", "revoked": False}

        await session.execute(
            text(
                "INSERT INTO mandate.revocations (mandate_id, reason_code, actor_ref) VALUES (:id, :reason, :actor)"
            ),
            {
                "id": mandate_id,
                "reason": body.reason_code,
                "actor": _actor_id(principal),
            },
        )

        reserved_result = await session.execute(
            text(
                "SELECT reservation_id, amount_minor FROM mandate.spend_reservations "
                "WHERE mandate_id = :id AND state = 'RESERVED'"
            ),
            {"id": mandate_id},
        )
        reserved_rows = reserved_result.mappings().all()
        for r in reserved_rows:
            await repo.set_reservation_state(
                session,
                str(r["reservation_id"]),
                "RELEASED",
                release_reason="MANDATE_REVOKED",
            )
            await repo.adjust_spend(
                session, mandate_id, reserved_delta=-r["amount_minor"]
            )

        revoked_event_id = repo.deterministic_event_id(mandate_id, "mandate.revoked")
        await repo.insert_outbox_event(
            session,
            event_type="mandate.revoked",
            mandate_id=mandate_id,
            event_id=revoked_event_id,
            payload={
                "mandate_id": mandate_id,
                "mandate_hash": mandate_row["mandate_hash"],
                "revoked_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "reason_code": body.reason_code,
                "revoke_effect": mandate_row["revoke_effect"],
                "released_reservations": len(reserved_rows),
            },
        )

        return {
            "mandate_id": mandate_id,
            "status": "revoked",
            "revoked_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "released_reservations": len(reserved_rows),
            "revoke_effect": mandate_row["revoke_effect"],
            "earned_protection_unchanged": True,
            "message_code": "FUTURE_PURCHASES_STOPPED",
        }


@router.post("/mandates/{mandate_id}/evaluate")
async def evaluate_mandate(
    mandate_id: str,
    body: EvaluateRequest,
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
        mandate_row, spend_row, revocation_row = await _load_mandate_context(
            session, mandate_id
        )
        integrity_ok, failed_check = repo.verify_integrity(
            mandate_row, spend_row, settings, bare_secrets
        )
        if not integrity_ok:
            await _emit_integrity_failed_if_needed(
                session, mandate_id, failed_check, mandate_row["hmac_key_id"]
            )

        now = repo.now_utc()
        status = mandate_logic.derive_status(
            revoked=revocation_row is not None,
            expires_at=mandate_row["expires_at"],
            spent_minor=spend_row["spent_minor"],
            max_total_minor=mandate_row["max_total_minor"],
            now=now,
        )
        remaining = _remaining(
            spend_row["max_total_minor"],
            spend_row["spent_minor"],
            spend_row["reserved_minor"],
        )
        # Cumulative cap enforcement (spec.md sec 4 step 6): the caller (checkout) has no
        # standing reservation against this mandate's own spend/reserved ledger yet --
        # checkout tracks its own in-flight/completed order totals and reports them here
        # each call via `committed_minor`, since nothing currently calls this mandate's
        # reservation lifecycle (POST .../reservations, authorize-capture, commit,
        # release) to keep `spent_minor`/`reserved_minor` in sync with checkout's orders.
        # Without this, `remaining` never reflects prior carts and the same mandate could
        # approve an unbounded number of carts under its cap.
        committed_minor = max(0, body.committed_minor or 0)
        remaining = max(0, remaining - committed_minor)
        result = mandate_logic.evaluate_cart(
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
        return {
            "decision": result.decision,
            "hard_blocks": result.hard_blocks,
            "advisory_flags": result.advisory_flags,
            "mandate": {
                "mandate_id": mandate_id,
                "mandate_hash": mandate_row["mandate_hash"],
                "status": status,
                "remaining_minor": remaining,
                "policy_version": mandate_row["policy_version"],
            },
            "evaluated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
