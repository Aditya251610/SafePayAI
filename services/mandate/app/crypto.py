"""canon.v1 canonical JSON, hashing, HMAC and free-text validation.

Per mandate/spec.md section 3. Not a claim of full RFC 8785 conformance (I).
No business logic beyond byte-exact determinism; callers build the dict to hash.
"""

from __future__ import annotations

import hashlib
import hmac as hmac_mod
import json
import unicodedata

from app.errors import MandateError

# Unicode general categories rejected in free text (bidi/zero-width/control/etc).
_REJECTED_CATEGORIES = {"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"}


class CanonError(ValueError):
    pass


def nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def validate_free_text(
    value: str, field: str, max_chars: int, *, allow_empty: bool = False
) -> str:
    """Trims, NFC-normalizes and validates free text per spec.md section 3.4.

    Raises MandateError 422 VALIDATION_ERROR (never echoes the offending text).
    """
    if not isinstance(value, str):
        raise MandateError(
            422, "VALIDATION_ERROR", "invalid text field", {"field": field}
        )
    text = nfc(value).strip()
    if not text and not allow_empty:
        raise MandateError(
            422, "VALIDATION_ERROR", "field must not be empty", {"field": field}
        )
    if len(text) > max_chars:
        raise MandateError(422, "VALIDATION_ERROR", "field too long", {"field": field})
    for ch in text:
        if ch in ("\n", "\r", "\t"):
            raise MandateError(
                422,
                "VALIDATION_ERROR",
                "field contains line-break characters",
                {"field": field},
            )
        if unicodedata.category(ch) in _REJECTED_CATEGORIES:
            raise MandateError(
                422,
                "VALIDATION_ERROR",
                "field contains disallowed characters",
                {"field": field},
            )
    try:
        text.encode("utf-8", "strict")
    except UnicodeEncodeError as exc:
        raise MandateError(
            422, "VALIDATION_ERROR", "field contains invalid unicode", {"field": field}
        ) from exc
    return text


def _canon_default(obj: object) -> object:
    raise CanonError(f"non-canonical type: {type(obj)!r}")


def _reject_floats(obj: object) -> None:
    if isinstance(obj, float):
        raise CanonError("floats are rejected in canonical JSON")
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                raise CanonError("non-string key in canonical JSON")
            _reject_floats(v)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _reject_floats(item)
    elif obj is None:
        raise CanonError("null is rejected in canonical JSON")
    elif isinstance(obj, int) and not isinstance(obj, bool):
        if abs(obj) > 2**53 - 1:
            raise CanonError("integer exceeds canonical JSON safe range")
    elif isinstance(obj, (str, bool)):
        if isinstance(obj, str):
            # unpaired surrogate check
            obj.encode("utf-8", "strict")
    else:
        raise CanonError(f"non-canonical type: {type(obj)!r}")


def _nfc_normalize(obj: object) -> object:
    if isinstance(obj, str):
        return nfc(obj)
    if isinstance(obj, dict):
        return {k: _nfc_normalize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_nfc_normalize(item) for item in obj]
    return obj


def canonical_json_bytes(obj: dict) -> bytes:
    """canon.v1: sorted keys (by code point), no whitespace, UTF-8, NFC strings,
    integers only, no nulls."""
    _reject_floats(obj)
    normalized = _nfc_normalize(obj)
    text = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_canon_default,
    )
    return text.encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canon_hash(obj: dict) -> str:
    return sha256_hex(canonical_json_bytes(obj))


MANDATE_HMAC_DOMAIN = b"mw.mandate.v1"
GRANT_HMAC_DOMAIN = b"mw.grant.v1"


def compute_hmac(
    key: bytes, domain: bytes, hash_bytes: bytes, buyer_id: str, nonce: str
) -> str:
    mac = hmac_mod.new(key, digestmod=hashlib.sha256)
    mac.update(domain)
    mac.update(b"\x00")
    mac.update(hash_bytes)
    mac.update(b"\x00")
    mac.update(buyer_id.encode("utf-8"))
    mac.update(b"\x00")
    mac.update(nonce.encode("utf-8"))
    return mac.hexdigest()


def verify_hmac(
    key: bytes,
    domain: bytes,
    hash_bytes: bytes,
    buyer_id: str,
    nonce: str,
    expected_hex: str,
) -> bool:
    computed = compute_hmac(key, domain, hash_bytes, buyer_id, nonce)
    return hmac_mod.compare_digest(computed, expected_hex)
