"""Internal JWT minting (spec.md section 7).

`libs/common.auth.jwt.mint_service_token` (the shared helper this project asks
every service to use instead of reimplementing JWT mint/verify) only accepts a
subject + `ServiceJWTConfig` (iss/aud/kid/ttl) and emits `iss, sub, aud, iat, exp` -
it has no parameter for the richer claim set spec.md section 7 requires
(`act`, `role`, `scope`, `jti`, `req`, `sid`, `mandate_id`). Per the task brief,
libs/common internals are out of scope to edit. `tokens/mint.py` is itself listed
in spec.md section 2 as api-gateway's own module (not a libs/common module) whose
job is exactly this claim assembly, so it builds on the same algorithm/key config
shape (`ServiceJWTConfig`) and calls PyJWT directly (already a direct dependency of
this service, not a reimplementation of the shared helper's job - gateway is the
only service that mints at all).
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterable

import jwt

from app.deps import Principal
from app.settings import Settings, get_settings
from app.tokens.keys import load_current_signing_key


def mint_for_upstream(
    principal: Principal | None,
    *,
    audience: str,
    request_id: str,
    scope: Iterable[str] = (),
    auth_method: str = "session",
    mandate_id: str | None = None,
    settings: Settings | None = None,
) -> str:
    """`principal` is an `app.deps.Principal` (or None for pure system calls, e.g.
    the tick poller). One token per upstream call; never reused across `aud`
    (spec.md section 7)."""
    settings = settings or get_settings()
    key = load_current_signing_key(settings)
    if key.private_key_pem is None:
        raise RuntimeError("no private signing key available to mint tokens")

    now = int(time.time())
    ttl = min(max(settings.internal_token_ttl_s, 1), 120)  # hard max 120s, ADR-006

    if principal is not None:
        sub = principal.actor_id
        role = principal.role
        act = {
            "actor_type": principal.actor_type,
            "actor_id": principal.actor_id,
            "role": principal.role,
            "auth_method": auth_method,
            "display_name": principal.display_name,
        }
        sid = principal.sid_hash
    else:
        sub = "svc:poller"
        role = None
        act = {
            "actor_type": "system",
            "actor_id": sub,
            "role": None,
            "auth_method": auth_method,
        }
        sid = None

    claims: dict = {
        "iss": "api-gateway",
        "sub": sub,
        "aud": audience,
        "iat": now,
        "exp": now + ttl,
        "jti": str(uuid.uuid4()),
        "req": request_id,
        "act": act,
        "role": role,
        "scope": list(scope),
        "sid": sid,
    }
    if mandate_id is not None:
        claims["mandate_id"] = mandate_id

    return jwt.encode(
        claims, key.private_key_pem, algorithm="RS256", headers={"kid": key.kid}
    )


def mint_system_token(
    audience: str, *, request_id: str | None = None, settings: Settings | None = None
) -> str:
    """`sub=svc:poller` system token for `/api/ops/tick` (spec.md REQ-GW-044)."""
    return mint_for_upstream(
        None,
        audience=audience,
        request_id=request_id or str(uuid.uuid4()),
        scope=["system"],
        auth_method="tick_secret",
        settings=settings,
    )
