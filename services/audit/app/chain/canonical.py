"""General-purpose canonicalizer for audit chain content objects (spec.md sec 4).

RFC 8785 (JSON Canonicalization Scheme) rules as spelled out in spec.md sec 4:
  - UTF-8 encoding.
  - Object keys sorted by UTF-16 code unit.
  - No whitespace.
  - Minimal string escapes.
  - Absent optional keys omitted (never a `null` placeholder).
  - Numbers: integers only -- floats are FORBIDDEN (money is integer minor units; this
    removes JCS's float-formatting edge cases entirely, per spec.md sec 4).
  - Strings: Unicode NFC normalized; lone surrogates rejected.

This is the GENERAL canonicalizer for any event content object (any producer, any event
type). It is distinct from `migrations/versions/0001_baseline.py`'s `_jcs_bytes`, which is
a minimal helper scoped only to the fixed, all-ASCII genesis payload (see that migration's
own docstring item 3). `tests/unit/test_canonical_hashing.py` cross-checks that both
produce byte-identical output for the genesis content object, so the two implementations
cannot silently drift (spec.md sec 4's byte-identical-output goal, risk R5 in prd.md).
"""

from __future__ import annotations

import json
import unicodedata
from typing import Any


class CanonicalizationError(ValueError):
    """Raised when content cannot be canonicalized per spec.md sec 4."""


def _check_no_lone_surrogate(s: str) -> None:
    for ch in s:
        cp = ord(ch)
        if 0xD800 <= cp <= 0xDFFF:
            raise CanonicalizationError(f"lone surrogate in string: U+{cp:04X}")


def _normalize_str(s: str) -> str:
    _check_no_lone_surrogate(s)
    return unicodedata.normalize("NFC", s)


def _clean(value: Any) -> Any:
    """Recursively NFC-normalizes strings, rejects floats, drops `None` dict values.

    `None` dict values are dropped (not emitted as `null`) per spec.md sec 4 "absent
    optional keys omitted (never null placeholders)". A `None` appearing as a bare list
    element or top-level value (not a dict value) is left alone -- the content schema
    (spec.md sec 4) never places `null` there, but this function does not invent a
    stricter rule than the spec states.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        raise CanonicalizationError("floats are forbidden in audit content (spec.md sec 4)")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return _normalize_str(value)
    if isinstance(value, list):
        return [_clean(v) for v in value]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if not isinstance(k, str):
                raise CanonicalizationError(f"non-string key: {k!r}")
            if v is None:
                continue
            out[_normalize_str(k)] = _clean(v)
        return out
    raise CanonicalizationError(f"unsupported type in audit content: {type(value)!r}")


def clean_for_compare(value: Any) -> Any:
    """Public entry point to `_clean`'s null-dropping/NFC-normalizing pass, for callers
    that need to compare a raw (uncleaned) value against something derived from
    `canonicalize()` -- e.g. verify.py comparing the `payload` JSONB column (stored with
    nulls intact) against the payload embedded in the already-canonicalized `canonical`
    column (nulls dropped). Comparing a raw value directly against a canonicalized one
    without first applying this would treat every null-valued payload field as tampering
    (spec.md sec 4's "absent optional keys omitted, never null placeholders" is a
    canonicalization-time transform, not a storage-time one -- the raw payload column is
    deliberately stored as submitted, for human/debug legibility)."""
    return _clean(value)


def canonicalize(content: dict[str, Any]) -> bytes:
    """Produces the exact UTF-8 bytes that get hashed for a content object.

    Key sort note: Python's default string comparison is by Unicode code point, which
    coincides with UTF-16 code unit order for every key this schema ever uses (spec.md
    sec 4's fixed key set: `v`, `chain_id`, `event_id`, ... plus payload keys, which by
    the redaction rules (spec.md sec 6) are themselves plain ASCII identifiers) -- there
    are no non-BMP characters in any key here, so code-point sort == UTF-16-code-unit
    sort (RFC 8785 sec 3.2.3 only diverges from code-point sort for surrogate-pair keys,
    which cannot occur for ASCII identifier keys).
    """
    cleaned = _clean(content)
    if not isinstance(cleaned, dict):
        raise CanonicalizationError("content object must be a JSON object")
    return json.dumps(cleaned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def reject_floats(payload: Any) -> None:
    """Standalone float-rejection pass usable before full canonicalization (api.md sec 1
    `422 FLOAT_FORBIDDEN`), so callers can surface the specific error code instead of a
    generic canonicalization failure."""
    _clean(payload)
