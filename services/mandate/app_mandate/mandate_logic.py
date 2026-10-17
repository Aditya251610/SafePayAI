"""Normalization, rendering, canonical hashing, state derivation and evaluate.

Pure functions per mandate/spec.md sections 3-6. No DB access here (routers/repo.py
own persistence); this module is deliberately I/O-free so it can be property-tested.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app_mandate.crypto import canon_hash, nfc, sha256_hex, validate_free_text
from app_mandate.errors import MandateError
from app_mandate.schemas.terms import MandateTermsInput
from app_mandate.settings import Settings

CANON_VERSION = "canon.v1"
SCHEMA_VERSION = "mandate.v1"
RENDER_VERSION = "render.v1"
REVOKE_EFFECT = "FUTURE_ONLY"
KNOWN_KINDS = ("LATE", "LOST")
MERCHANT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

# T25: banned phrases must never appear in rendered text.
BANNED_PHRASES = (
    "PayPal-backed",
    "verified by PayPal",
    "legally binding",
    "non-repudiable",
    "tamper-proof",
    "guaranteed",
    "insured",
)


def parse_utc_timestamp(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not TIMESTAMP_RE.match(value):
        raise MandateError(
            422,
            "VALIDATION_ERROR",
            "timestamp must be YYYY-MM-DDTHH:MM:SSZ",
            {"field": field},
        )
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise MandateError(
            422, "VALIDATION_ERROR", "invalid timestamp", {"field": field}
        ) from exc


def format_utc_timestamp(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class NormalizedTerms:
    as_dict: dict


def normalize_terms(
    input_terms: MandateTermsInput, settings: Settings, *, now: datetime
) -> dict:
    """Validates and materializes defaults. Raises MandateError on any violation."""
    if input_terms.currency != settings.currency:
        raise MandateError(
            422, "UNSUPPORTED_CURRENCY", "unsupported currency", {"field": "currency"}
        )

    if (
        input_terms.max_total_minor <= 0
        or input_terms.max_total_minor > settings.max_total_ceiling_minor
    ):
        raise MandateError(
            422,
            "TERMS_OUT_OF_BOUNDS",
            "max_total_minor out of bounds",
            {"field": "max_total_minor"},
        )

    max_qty = (
        input_terms.max_qty_per_line
        if input_terms.max_qty_per_line is not None
        else settings.default_max_qty_per_line
    )
    if max_qty < 1 or max_qty > settings.max_qty_per_line_ceiling:
        raise MandateError(
            422,
            "TERMS_OUT_OF_BOUNDS",
            "max_qty_per_line out of bounds",
            {"field": "max_qty_per_line"},
        )

    if (
        not input_terms.merchant_allowlist
        or len(input_terms.merchant_allowlist) > settings.max_merchants
    ):
        raise MandateError(
            422,
            "TERMS_OUT_OF_BOUNDS",
            "merchant_allowlist size out of bounds",
            {"field": "merchant_allowlist"},
        )
    seen_ids: set[str] = set()
    merchants: list[dict] = []
    for entry in input_terms.merchant_allowlist:
        if not MERCHANT_ID_RE.match(entry.merchant_id):
            raise MandateError(
                422,
                "VALIDATION_ERROR",
                "invalid merchant_id",
                {"field": "merchant_allowlist.merchant_id"},
            )
        if entry.merchant_id in seen_ids:
            raise MandateError(
                422,
                "VALIDATION_ERROR",
                "duplicate merchant_id",
                {"field": "merchant_allowlist.merchant_id"},
            )
        seen_ids.add(entry.merchant_id)
        display_name = validate_free_text(
            entry.display_name, "merchant_allowlist.display_name", 64
        )
        merchants.append(
            {"merchant_id": entry.merchant_id, "display_name": display_name}
        )
    merchants.sort(key=lambda m: m["merchant_id"])

    intent_text = validate_free_text(
        input_terms.intent_text, "intent_text", settings.intent_max_chars
    )

    expires_dt = parse_utc_timestamp(input_terms.expires_at, "expires_at")
    min_ok = now + timedelta(seconds=settings.min_expiry_seconds)
    max_ok = now + timedelta(seconds=settings.max_expiry_seconds)
    if not (min_ok <= expires_dt <= max_ok):
        raise MandateError(
            422,
            "TERMS_OUT_OF_BOUNDS",
            "expires_at out of bounds",
            {"field": "expires_at"},
        )

    kinds = sorted(set(input_terms.protection.kinds_covered))
    if not kinds or any(k not in KNOWN_KINDS for k in kinds):
        raise MandateError(
            422,
            "VALIDATION_ERROR",
            "invalid kinds_covered",
            {"field": "protection.kinds_covered"},
        )
    max_refund = input_terms.protection.max_refund_minor
    if (
        max_refund <= 0
        or max_refund > input_terms.max_total_minor
        or max_refund > settings.refund_cap_ceiling_minor
    ):
        raise MandateError(
            422,
            "TERMS_OUT_OF_BOUNDS",
            "max_refund_minor out of bounds",
            {"field": "protection.max_refund_minor"},
        )
    deliver_by = input_terms.protection.deliver_by_days
    if not (settings.deliver_by_days_min <= deliver_by <= settings.deliver_by_days_max):
        raise MandateError(
            422,
            "TERMS_OUT_OF_BOUNDS",
            "deliver_by_days out of bounds",
            {"field": "protection.deliver_by_days"},
        )

    revoke_effect = input_terms.revoke_effect or REVOKE_EFFECT
    if revoke_effect != REVOKE_EFFECT:
        raise MandateError(
            422,
            "VALIDATION_ERROR",
            "unsupported revoke_effect",
            {"field": "revoke_effect"},
        )

    policy_version = input_terms.policy_version or settings.policy_version
    if policy_version != settings.policy_version:
        raise MandateError(
            409,
            "POLICY_VERSION_MISMATCH",
            "policy_version mismatch",
            {"field": "policy_version"},
        )

    return {
        "currency": input_terms.currency,
        "max_total_minor": input_terms.max_total_minor,
        "max_qty_per_line": max_qty,
        "merchant_allowlist": merchants,
        "intent_text": intent_text,
        "expires_at": format_utc_timestamp(expires_dt),
        "protection": {
            "kinds_covered": kinds,
            "max_refund_minor": max_refund,
            "deliver_by_days": deliver_by,
        },
        "revoke_effect": revoke_effect,
        "policy_version": policy_version,
    }


def terms_digest(normalized: dict) -> str:
    """Binds a nonce to the exact previewed terms (spec.md section 10.1)."""
    return canon_hash(normalized)


def _format_money(minor: int) -> str:
    sign = "-" if minor < 0 else ""
    minor_abs = abs(minor)
    return f"USD {sign}{minor_abs // 100}.{minor_abs % 100:02d}"


def _format_display_date(iso_ts: str) -> str:
    dt = parse_utc_timestamp(iso_ts, "expires_at")
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def _kinds_words(kinds: list[str]) -> str:
    words = [k.lower() for k in kinds]
    if len(words) == 1:
        return words[0]
    return " or ".join(words)


def render_text(normalized: dict) -> str:
    """render.v1: pure function of normalized terms only (spec.md section 4)."""
    merchants_str = "; ".join(
        f"{m['display_name']} ({m['merchant_id']})"
        for m in normalized["merchant_allowlist"]
    )
    protection = normalized["protection"]
    sentences = [
        "DEMO MANDATE - sandbox only, not a legal agreement.",
        f"Your shopping agent may buy only from: {merchants_str}.",
        f"All purchases under this mandate together may not exceed {_format_money(normalized['max_total_minor'])}, including fees.",
        f"No single item line may exceed {normalized['max_qty_per_line']} units.",
        f'Purpose you stated: "{normalized["intent_text"]}"',
        (
            f"This mandate expires {_format_display_date(normalized['expires_at'])}. You can revoke it at any time. "
            "Revoking stops new purchases; refund protection already earned on completed purchases stays."
        ),
        (
            f"If an order covered by this mandate is {_kinds_words(protection['kinds_covered'])} "
            f"(not delivered within {protection['deliver_by_days']} days of purchase, on the demo clock), "
            f"a refund of up to {_format_money(protection['max_refund_minor'])} is pre-approved. "
            "The refund is merchant-funded via a PayPal sandbox refund."
        ),
    ]
    text = "\n\n".join(sentences)
    return nfc(text)


def screen_text_hash(text: str) -> str:
    return sha256_hex(text.encode("utf-8"))


def build_mandate_canonical_object(
    *,
    mandate_id: str,
    buyer_id: str,
    normalized: dict,
    nonce: str,
    created_at: str,
    screen_text_hash_value: str,
) -> dict:
    return {
        "canon": CANON_VERSION,
        "schema": SCHEMA_VERSION,
        "render": RENDER_VERSION,
        "mandate_id": mandate_id,
        "buyer_id": buyer_id,
        "currency": normalized["currency"],
        "max_total_minor": normalized["max_total_minor"],
        "max_qty_per_line": normalized["max_qty_per_line"],
        "merchant_allowlist": normalized["merchant_allowlist"],
        "intent_text": normalized["intent_text"],
        "expires_at": normalized["expires_at"],
        "protection": normalized["protection"],
        "revoke_effect": normalized["revoke_effect"],
        "policy_version": normalized["policy_version"],
        "nonce": nonce,
        "created_at": created_at,
        "screen_text_hash": screen_text_hash_value,
    }


# ---------------------------------------------------------------------------
# State derivation (spec.md section 5)
# ---------------------------------------------------------------------------


def derive_status(
    *,
    revoked: bool,
    expires_at: datetime,
    spent_minor: int,
    max_total_minor: int,
    now: datetime,
    exhaust_dust_minor: int = 0,
) -> str:
    if revoked:
        return "revoked"
    if now >= expires_at:
        return "expired"
    if spent_minor >= max_total_minor - exhaust_dust_minor:
        return "exhausted"
    return "active"


# ---------------------------------------------------------------------------
# Evaluate (spec.md section 6) - pure, no writes, no network.
# ---------------------------------------------------------------------------


@dataclass
class EvaluateResult:
    decision: str
    hard_blocks: list[dict]
    advisory_flags: list[dict]


def evaluate_cart(
    *,
    integrity_ok: bool,
    status: str,
    merchant_allowlist: list[dict],
    max_qty_per_line: int,
    currency: str,
    remaining_minor: int,
    cart: dict,
    expires_at: datetime,
    now: datetime,
    near_cap_percent: int,
    expires_soon_seconds: int,
) -> EvaluateResult:
    hard_blocks: list[dict] = []

    if not integrity_ok:
        return EvaluateResult(
            "BLOCK", [{"code": "MANDATE_INTEGRITY_FAILED", "details": {}}], []
        )

    if status == "revoked":
        hard_blocks.append({"code": "MANDATE_REVOKED", "details": {}})
    if status == "expired":
        hard_blocks.append({"code": "MANDATE_EXPIRED", "details": {}})
    if status == "exhausted":
        hard_blocks.append({"code": "MANDATE_EXHAUSTED", "details": {}})

    allowed_ids = {m["merchant_id"] for m in merchant_allowlist}
    offending_merchants = sorted(
        {
            line["merchant_id"]
            for line in cart["lines"]
            if line["merchant_id"] not in allowed_ids
        }
    )
    if offending_merchants:
        hard_blocks.append(
            {
                "code": "MERCHANT_NOT_ALLOWED",
                "details": {"merchant_ids": offending_merchants},
            }
        )

    total_minor = cart["total_minor"]
    if total_minor > remaining_minor:
        hard_blocks.append(
            {
                "code": "OVER_CAP",
                "details": {
                    "total_minor": total_minor,
                    "remaining_minor": remaining_minor,
                },
            }
        )

    unknown_skus = sorted(
        {line["sku"] for line in cart["lines"] if not line["sku_known"]}
    )
    if unknown_skus:
        hard_blocks.append({"code": "UNKNOWN_SKU", "details": {"skus": unknown_skus}})

    qty_over = sorted(
        {line["sku"] for line in cart["lines"] if line["qty"] > max_qty_per_line}
    )
    if qty_over:
        hard_blocks.append(
            {
                "code": "QTY_CAP",
                "details": {"skus": qty_over, "max_qty_per_line": max_qty_per_line},
            }
        )

    if cart["currency"] != currency:
        hard_blocks.append({"code": "CURRENCY_MISMATCH", "details": {}})

    price_mismatch = sorted(
        {
            line["sku"]
            for line in cart["lines"]
            if line.get("stated_unit_minor") is not None
            and line["stated_unit_minor"] != line["unit_minor"]
        }
    )
    if price_mismatch:
        hard_blocks.append(
            {"code": "PRICE_MISMATCH", "details": {"skus": price_mismatch}}
        )

    arithmetic_bad = False
    for line in cart["lines"]:
        if line["line_minor"] != line["qty"] * line["unit_minor"]:
            arithmetic_bad = True
            break
    if not arithmetic_bad and total_minor != sum(
        line["line_minor"] for line in cart["lines"]
    ):
        arithmetic_bad = True
    if arithmetic_bad:
        hard_blocks.append({"code": "CART_ARITHMETIC_MISMATCH", "details": {}})

    advisory_flags: list[dict] = []
    if remaining_minor > 0 and total_minor * 100 >= remaining_minor * near_cap_percent:
        advisory_flags.append({"code": "NEAR_CAP"})
    if (expires_at - now).total_seconds() < expires_soon_seconds:
        advisory_flags.append({"code": "EXPIRES_SOON"})
    if len({line["merchant_id"] for line in cart["lines"]}) > 1:
        advisory_flags.append({"code": "MULTI_MERCHANT"})

    decision = "ALLOW" if not hard_blocks else "BLOCK"
    return EvaluateResult(decision, hard_blocks, advisory_flags)


def check_malformed_cart(cart: dict) -> None:
    if not cart["lines"]:
        raise MandateError(422, "MALFORMED_CART", "cart has no lines", {})
    seen: set[str] = set()
    for line in cart["lines"]:
        if line["sku"] in seen:
            raise MandateError(
                422, "MALFORMED_CART", "duplicate sku in cart", {"sku": line["sku"]}
            )
        seen.add(line["sku"])
        if line["qty"] < 1:
            raise MandateError(
                422, "MALFORMED_CART", "qty must be >= 1", {"sku": line["sku"]}
            )
