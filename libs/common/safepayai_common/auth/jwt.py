"""Internal service-JWT mint/verify. No business logic — see architecture/auth-gateway.md."""

from __future__ import annotations

import time
from dataclasses import dataclass

import jwt


@dataclass(frozen=True)
class ServiceJWTConfig:
    issuer: str
    audience: str
    signing_key_pem: str
    kid: str
    ttl_seconds: int = 60


def mint_service_token(subject: str, config: ServiceJWTConfig) -> str:
    now = int(time.time())
    payload = {
        "iss": config.issuer,
        "aud": config.audience,
        "sub": subject,
        "iat": now,
        "exp": now + config.ttl_seconds,
    }
    return jwt.encode(payload, config.signing_key_pem, algorithm="RS256", headers={"kid": config.kid})


def verify_service_token(token: str, jwks_client: jwt.PyJWKClient, audience: str, trusted_issuers: list[str]) -> dict:
    """Raises jwt.PyJWTError subclasses on any failure. Callers must fail closed (401/403), never swallow."""
    signing_key = jwks_client.get_signing_key_from_jwt(token)
    claims = jwt.decode(token, signing_key.key, algorithms=["RS256"], audience=audience)
    if claims.get("iss") not in trusted_issuers:
        raise jwt.InvalidIssuerError(f"issuer {claims.get('iss')!r} not trusted")
    return claims
