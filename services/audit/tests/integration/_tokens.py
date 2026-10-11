"""Test-only service-JWT minting against the HS256 secret configured in
PS_AUDIT_TRUSTED_ISSUERS by conftest.py. Not a reimplementation of
libs/common/safepayai_common/auth/jwt.py (that helper mints/verifies against a real
JWKS endpoint; audit's own deps.py intentionally uses a static trusted-issuer map with
no network fetch, per spec.md sec 5/8 -- see deps.py's module docstring). This module
just produces tokens shaped the way deps.py expects to verify them.
"""

from __future__ import annotations

import time
from typing import Any

import jwt

TEST_SECRET = "test-only-hs256-secret-not-for-production-use"
TEST_KID = "test-kid"
TEST_ISSUER = "test-issuer"
TEST_AUDIENCE = "audit"


def mint_token(
    sub: str,
    *,
    act: dict[str, Any] | None = None,
    request_id: str = "r-test",
    trace_id: str = "t-test",
    exp_seconds: int = 60,
    aud: str = TEST_AUDIENCE,
) -> str:
    now = int(time.time())
    payload: dict[str, Any] = {
        "iss": TEST_ISSUER,
        "aud": aud,
        "sub": sub,
        "iat": now,
        "exp": now + exp_seconds,
        "req": request_id,
        "trace_id": trace_id,
    }
    if act is not None:
        payload["act"] = act
    return jwt.encode(payload, TEST_SECRET, algorithm="HS256", headers={"kid": TEST_KID})
