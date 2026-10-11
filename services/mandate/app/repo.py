"""DB access layer for mandate: raw SQL via SQLAlchemy Core text(), no ORM models.

Centralizes the locking protocol (spec.md section 7.3), integrity check (3.3),
outbox inserts (ADR-003) and idempotency/nonce bookkeeping so routers stay thin.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.crypto import (
    MANDATE_HMAC_DOMAIN,
    canonical_json_bytes,
    sha256_hex,
    verify_hmac,
)
from app.errors import MandateError
from app.mandate_logic import build_mandate_canonical_object

EVENT_NAMESPACE = uuid.UUID("5a1d3b2e-0000-4000-8000-000000000001")


def deterministic_event_id(mandate_id: str, event_type: str, extra: str = "") -> str:
    name = f"{mandate_id}:{event_type}:{extra}"
    return str(uuid.uuid5(EVENT_NAMESPACE, name))


def now_utc() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Outbox (ADR-003): always inserted in the same transaction as the state change.
# ---------------------------------------------------------------------------


async def insert_outbox_event(
    session: AsyncSession,
    *,
    event_type: str,
    mandate_id: str,
    payload: dict,
    event_id: str | None = None,
    trace_id: str | None = None,
) -> None:
    eid = event_id or str(uuid.uuid4())
    await session.execute(
        text(
            """
            INSERT INTO mandate.outbox (event_id, type, version, aggregate_id, payload, trace_id)
            VALUES (:event_id, :type, 1, :aggregate_id, :payload, :trace_id)
            ON CONFLICT (event_id) DO NOTHING
            """
        ),
        {
            "event_id": eid,
            "type": event_type,
            "aggregate_id": mandate_id,
            "payload": to_jsonb_text(payload),
            "trace_id": trace_id,
        },
    )


def to_jsonb_text(payload: dict):
    import json

    return json.dumps(payload)


# ---------------------------------------------------------------------------
# Mandate row access
# ---------------------------------------------------------------------------

MANDATE_COLUMNS = """
    mandate_id, buyer_id, schema, currency, max_total_minor, max_qty_per_line,
    merchant_allowlist, intent_text, expires_at, protection, revoke_effect,
    policy_version, nonce, render_version, screen_text_hash, canonical_json,
    mandate_hash, hmac, hmac_alg, hmac_key_id, signed_at, created_at
"""


async def get_mandate_row(session: AsyncSession, mandate_id: str) -> dict | None:
    result = await session.execute(
        text(f"SELECT {MANDATE_COLUMNS} FROM mandate.mandates WHERE mandate_id = :id"),
        {"id": mandate_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def get_revocation_row(session: AsyncSession, mandate_id: str) -> dict | None:
    result = await session.execute(
        text("SELECT mandate_id, revoked_at, reason_code, actor_ref FROM mandate.revocations WHERE mandate_id = :id"),
        {"id": mandate_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def get_spend_row(session: AsyncSession, mandate_id: str) -> dict | None:
    result = await session.execute(
        text(
            "SELECT mandate_id, max_total_minor, spent_minor, reserved_minor, version "
            "FROM mandate.mandate_spend WHERE mandate_id = :id"
        ),
        {"id": mandate_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def lock_spend_row(session: AsyncSession, mandate_id: str, settings) -> dict:
    """Takes the mandate's row lock (spec.md section 7.3). Caller must already be
    inside a transaction (`async with session.begin():`)."""
    await session.execute(text(f"SET LOCAL lock_timeout = {int(settings.lock_timeout_ms)}"))
    await session.execute(text(f"SET LOCAL statement_timeout = {int(settings.statement_timeout_ms)}"))
    try:
        result = await session.execute(
            text(
                "SELECT mandate_id, max_total_minor, spent_minor, reserved_minor, version "
                "FROM mandate.mandate_spend WHERE mandate_id = :id FOR UPDATE"
            ),
            {"id": mandate_id},
        )
    except OperationalError as exc:
        raise MandateError(503, "LOCK_TIMEOUT", "lock acquisition timed out", {}) from exc
    row = result.mappings().first()
    if row is None:
        raise MandateError(404, "MANDATE_NOT_FOUND", "mandate not found", {})
    return dict(row)


# ---------------------------------------------------------------------------
# Integrity check (spec.md section 3.3)
# ---------------------------------------------------------------------------


def key_bytes_for(key_id: str, settings, bare_secrets) -> bytes | None:
    if key_id == settings.hmac_key_id and bare_secrets.mandate_hmac_key:
        return bare_secrets.mandate_hmac_key.encode("utf-8")
    if (
        settings.hmac_key_id_previous
        and key_id == settings.hmac_key_id_previous
        and bare_secrets.mandate_hmac_key_previous
    ):
        return bare_secrets.mandate_hmac_key_previous.encode("utf-8")
    return None


class IntegrityResult:
    def __init__(self) -> None:
        self.canonical_matches = False
        self.hash_matches = False
        self.hmac_valid = False
        self.key_known = False
        self.spend_row_consistent = False
        self.failed_check: str | None = None

    @property
    def ok(self) -> bool:
        return (
            self.canonical_matches
            and self.hash_matches
            and self.hmac_valid
            and self.key_known
            and self.spend_row_consistent
        )

    def as_dict(self) -> dict:
        return {
            "canonical_matches": self.canonical_matches,
            "hash_matches": self.hash_matches,
            "hmac_valid": self.hmac_valid,
            "key_known": self.key_known,
            "spend_row_consistent": self.spend_row_consistent,
        }


def verify_integrity_detailed(mandate_row: dict, spend_row: dict | None, settings, bare_secrets) -> IntegrityResult:
    res = IntegrityResult()
    if mandate_row["schema"] != "mandate.v1":
        res.failed_check = "SCHEMA_UNKNOWN"
        return res

    normalized = {
        "currency": mandate_row["currency"],
        "max_total_minor": mandate_row["max_total_minor"],
        "max_qty_per_line": mandate_row["max_qty_per_line"],
        "merchant_allowlist": mandate_row["merchant_allowlist"],
        "intent_text": mandate_row["intent_text"],
        "expires_at": mandate_row["expires_at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
        "protection": mandate_row["protection"],
        "revoke_effect": mandate_row["revoke_effect"],
        "policy_version": mandate_row["policy_version"],
    }
    rebuilt = build_mandate_canonical_object(
        mandate_id=str(mandate_row["mandate_id"]),
        buyer_id=mandate_row["buyer_id"],
        normalized=normalized,
        nonce=mandate_row["nonce"],
        created_at=mandate_row["created_at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
        screen_text_hash_value=mandate_row["screen_text_hash"],
    )
    rebuilt_bytes = canonical_json_bytes(rebuilt)
    res.canonical_matches = rebuilt_bytes == mandate_row["canonical_json"].encode("utf-8")
    if not res.canonical_matches:
        res.failed_check = "CANONICAL_MISMATCH"
        return res
    rebuilt_hash = sha256_hex(rebuilt_bytes)
    res.hash_matches = rebuilt_hash == mandate_row["mandate_hash"]
    if not res.hash_matches:
        res.failed_check = "HASH_MISMATCH"
        return res

    key = key_bytes_for(mandate_row["hmac_key_id"], settings, bare_secrets)
    res.key_known = key is not None
    if not res.key_known:
        res.failed_check = "KEY_UNKNOWN"
        return res
    hash_bytes = bytes.fromhex(rebuilt_hash)
    res.hmac_valid = verify_hmac(
        key, MANDATE_HMAC_DOMAIN, hash_bytes, mandate_row["buyer_id"], mandate_row["nonce"], mandate_row["hmac"]
    )
    if not res.hmac_valid:
        res.failed_check = "HMAC_INVALID"
        return res

    res.spend_row_consistent = spend_row is None or spend_row["max_total_minor"] == mandate_row["max_total_minor"]
    if not res.spend_row_consistent:
        res.failed_check = "SPEND_ROW_INCONSISTENT"
        return res

    return res


def verify_integrity(mandate_row: dict, spend_row: dict | None, settings, bare_secrets) -> tuple[bool, str | None]:
    res = verify_integrity_detailed(mandate_row, spend_row, settings, bare_secrets)
    return res.ok, res.failed_check


# ---------------------------------------------------------------------------
# Idempotency (spec.md section 10.2)
# ---------------------------------------------------------------------------


async def idempotency_lookup(session: AsyncSession, scope: str, key: str) -> dict | None:
    result = await session.execute(
        text("SELECT scope, key, request_hash, response FROM mandate.idempotency_keys WHERE scope = :scope AND key = :key"),
        {"scope": scope, "key": key},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def idempotency_store(session: AsyncSession, scope: str, key: str, request_hash: str, response: dict) -> None:
    await session.execute(
        text(
            "INSERT INTO mandate.idempotency_keys (scope, key, request_hash, response) "
            "VALUES (:scope, :key, :request_hash, :response)"
        ),
        {"scope": scope, "key": key, "request_hash": request_hash, "response": to_jsonb_text(response)},
    )


def request_hash_of(payload: dict) -> str:
    """Idempotency request fingerprint. Not the signed canon.v1 object - the raw
    request body may contain optional-and-omitted (null) fields, so this uses plain
    JSON canonicalization (sorted keys) rather than the strict no-null canon_hash."""
    import json

    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return sha256_hex(text.encode("utf-8"))


# ---------------------------------------------------------------------------
# Nonce (spec.md section 10.1)
# ---------------------------------------------------------------------------


async def insert_nonce(session: AsyncSession, nonce_hash: str, buyer_id: str, purpose: str, digest: str, ttl_seconds: int) -> None:
    await session.execute(
        text(
            "INSERT INTO mandate.nonces (nonce_hash, buyer_id, purpose, terms_digest, expires_at) "
            "VALUES (:nonce_hash, :buyer_id, :purpose, :digest, now() + make_interval(secs => :ttl))"
        ),
        {"nonce_hash": nonce_hash, "buyer_id": buyer_id, "purpose": purpose, "digest": digest, "ttl": ttl_seconds},
    )


async def check_nonce_valid(session: AsyncSession, nonce_hash: str, buyer_id: str, purpose: str, digest: str) -> None:
    """Read-only pre-check; the atomic consume happens via `consume_nonce` after the
    mandate row exists (nonce_uses.mandate_id has an FK to mandates)."""
    result = await session.execute(
        text(
            "SELECT 1 FROM mandate.nonces WHERE nonce_hash = :nonce_hash AND buyer_id = :buyer_id "
            "AND purpose = :purpose AND terms_digest = :digest AND expires_at > now()"
        ),
        {"nonce_hash": nonce_hash, "buyer_id": buyer_id, "purpose": purpose, "digest": digest},
    )
    if result.first() is None:
        raise MandateError(409, "NONCE_INVALID", "nonce is invalid, expired, or does not match terms", {})


async def consume_nonce(session: AsyncSession, nonce_hash: str, mandate_id: str) -> None:
    """INSERT-only consumption; PK violation = replay (data-architecture grant model)."""
    try:
        await session.execute(
            text("INSERT INTO mandate.nonce_uses (nonce_hash, mandate_id) VALUES (:nonce_hash, :mandate_id)"),
            {"nonce_hash": nonce_hash, "mandate_id": mandate_id},
        )
    except IntegrityError as exc:
        raise MandateError(409, "NONCE_INVALID", "nonce already used", {}) from exc


# ---------------------------------------------------------------------------
# Reservations (spec.md section 7.2)
# ---------------------------------------------------------------------------

RESERVATION_COLUMNS = """
    reservation_id, mandate_id, order_id, amount_minor, currency, proposal_hash,
    state, expires_at, authorized_at, captured_at, capture_id, release_reason,
    created_at, updated_at
"""


async def get_reservation_row(session: AsyncSession, reservation_id: str) -> dict | None:
    result = await session.execute(
        text(f"SELECT {RESERVATION_COLUMNS} FROM mandate.spend_reservations WHERE reservation_id = :id"),
        {"id": reservation_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def get_reservation_by_order(session: AsyncSession, mandate_id: str, order_id: str) -> dict | None:
    result = await session.execute(
        text(f"SELECT {RESERVATION_COLUMNS} FROM mandate.spend_reservations WHERE mandate_id = :m AND order_id = :o"),
        {"m": mandate_id, "o": order_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def insert_reservation(
    session: AsyncSession,
    *,
    reservation_id: str,
    mandate_id: str,
    order_id: str,
    amount_minor: int,
    currency: str,
    proposal_hash: str,
    expires_at: datetime,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO mandate.spend_reservations
                (reservation_id, mandate_id, order_id, amount_minor, currency, proposal_hash, state, expires_at)
            VALUES (:reservation_id, :mandate_id, :order_id, :amount_minor, :currency, :proposal_hash, 'RESERVED', :expires_at)
            """
        ),
        {
            "reservation_id": reservation_id,
            "mandate_id": mandate_id,
            "order_id": order_id,
            "amount_minor": amount_minor,
            "currency": currency,
            "proposal_hash": proposal_hash,
            "expires_at": expires_at,
        },
    )


async def set_reservation_state(session: AsyncSession, reservation_id: str, state: str, **fields) -> None:
    assignments = ["state = :state", "updated_at = now()"]
    params: dict = {"state": state, "id": reservation_id}
    for key, value in fields.items():
        assignments.append(f"{key} = :{key}")
        params[key] = value
    await session.execute(
        text(f"UPDATE mandate.spend_reservations SET {', '.join(assignments)} WHERE reservation_id = :id"),
        params,
    )


async def adjust_spend(session: AsyncSession, mandate_id: str, *, spent_delta: int = 0, reserved_delta: int = 0) -> None:
    await session.execute(
        text(
            """
            UPDATE mandate.mandate_spend
            SET spent_minor = spent_minor + :spent_delta,
                reserved_minor = reserved_minor + :reserved_delta,
                version = version + 1,
                updated_at = now()
            WHERE mandate_id = :id
            """
        ),
        {"id": mandate_id, "spent_delta": spent_delta, "reserved_delta": reserved_delta},
    )


# ---------------------------------------------------------------------------
# Protection grants (spec.md section 9.2)
# ---------------------------------------------------------------------------

GRANT_COLUMNS = """
    grant_id, mandate_id, order_id, capture_id, buyer_id, mandate_hash, terms,
    terms_hash, captured_amount_minor, captured_at, grant_hmac, hmac_key_id, created_at
"""


async def insert_grant(session: AsyncSession, **fields) -> None:
    columns = [
        "grant_id", "mandate_id", "order_id", "capture_id", "buyer_id", "mandate_hash",
        "terms", "terms_hash", "captured_amount_minor", "captured_at", "grant_hmac", "hmac_key_id",
    ]
    params = dict(fields)
    params["terms"] = to_jsonb_text(fields["terms"])
    placeholders = ", ".join(f":{c}" for c in columns)
    await session.execute(
        text(f"INSERT INTO mandate.protection_grants ({', '.join(columns)}) VALUES ({placeholders})"),
        params,
    )


async def get_grant_by_order(session: AsyncSession, order_id: str) -> dict | None:
    result = await session.execute(
        text(f"SELECT {GRANT_COLUMNS} FROM mandate.protection_grants WHERE order_id = :id"),
        {"id": order_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def get_grant_by_id(session: AsyncSession, grant_id: str) -> dict | None:
    result = await session.execute(
        text(f"SELECT {GRANT_COLUMNS} FROM mandate.protection_grants WHERE grant_id = :id"),
        {"id": grant_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None
