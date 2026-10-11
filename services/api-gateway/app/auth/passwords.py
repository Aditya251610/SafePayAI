"""argon2id password hashing (spec.md section 2, `auth/passwords.py`).

Includes a dummy-hash constant-time path (REQ-GW-002, GW-U12): verifying against an
unknown handle still runs an argon2 verify against a fixed dummy hash so the
response-time profile doesn't leak whether a handle exists. Never return a different
error for "unknown handle" vs "bad password" from the caller (see routers/auth.py).
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()

# A fixed, valid argon2id hash of a constant, never-used value, computed at import
# time. Used only so that the "unknown handle" path spends roughly the same CPU
# time as a real verify (GW-U12); it does not correspond to any real credential.
_DUMMY_HASH = _hasher.hash("safepayai-dummy-hash-no-such-account")


def hash_password(plaintext: str) -> str:
    return _hasher.hash(plaintext)


def verify_password(plaintext: str, password_hash: str | None) -> bool:
    """Returns True only on a real match. Always runs an argon2 verify, even when
    `password_hash` is None/unknown, against `_DUMMY_HASH` - so callers can treat
    "unknown handle" and "wrong password" identically without a timing tell."""
    target = password_hash or _DUMMY_HASH
    try:
        _hasher.verify(target, plaintext)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    # Dummy path (password_hash is None) always reports failure regardless of verify() outcome.
    return password_hash is not None
