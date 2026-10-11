"""Internal JWT minting wrapper (spec.md section 7).

Thin wrapper around safepayai_common.auth.jwt.mint_service_token - api-gateway is
the one service that mints (every other service only verifies). Not wired into any
route yet (Wave 4: all routes are stubs except health/readyz); kept here so the
module exists per spec.md section 2's internal module list (`tokens/mint.py`).
"""

from __future__ import annotations

from safepayai_common.auth.jwt import ServiceJWTConfig, mint_service_token

from app.settings import Settings, get_settings


def mint_for_upstream(subject: str, audience: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    if not settings.signing_key_pem:
        raise RuntimeError("PS_APIGATEWAY_SIGNING_KEY_PEM is not configured")
    config = ServiceJWTConfig(
        issuer="api-gateway",
        audience=audience,
        signing_key_pem=settings.signing_key_pem,
        kid=settings.signing_kid,
        ttl_seconds=settings.internal_token_ttl_s,
    )
    return mint_service_token(subject, config)
