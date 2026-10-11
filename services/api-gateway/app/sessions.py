"""Session cookie helpers: hashing only (per spec.md section 4.1).

Raw sid is never stored or logged; only SHA-256(sid) is persisted/queried. This
module is infra (same lane as a JWT-verify helper elsewhere), not business logic:
it does not decide who may do what, only how a cookie value maps to a lookup key.
"""

from __future__ import annotations

import hashlib


def hash_sid(raw_sid: str) -> str:
    return hashlib.sha256(raw_sid.encode("utf-8")).hexdigest()
