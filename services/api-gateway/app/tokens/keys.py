"""Signing-key loading and JWKS document assembly (spec.md section 2 `tokens/keys.py`,
section 7, section 15/R15).

Deviation flagged (see final report): spec.md section 7 asks for EdDSA/Ed25519.
`libs/common.auth.jwt` (the shared mint/verify helper this service is required to
use rather than reimplement) only supports RS256. Per the task brief, libs/common
internals are out of scope to edit, so this module follows what the shared helper
actually supports: RSA keypairs, alg RS256, JWKS `kty=RSA`. The claim shape (`iss`,
`sub`, `aud`, `act`, `role`, `scope`, `jti`, `sid`, `kid`) still matches spec.md
section 7 exactly; only the asymmetric algorithm differs from the spec's preference.

Current key: `PS_APIGATEWAY_SIGNING_KEY_PEM` (RSA private key, PEM) + `PS_APIGATEWAY_SIGNING_KID`.
Previous keys (rotation overlap): `PS_APIGATEWAY_PREVIOUS_PUBLIC_KEYS`, a JSON list of
`{"kid": "...", "public_key_pem": "..."}` objects - public keys only, no private
material, per spec.md section 7's rotation procedure.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from jwt.algorithms import RSAAlgorithm

from app.settings import Settings


@dataclass(frozen=True)
class SigningKey:
    kid: str
    public_key_pem: str
    private_key_pem: str | None = None


def load_current_signing_key(settings: Settings) -> SigningKey:
    if not settings.signing_key_pem:
        raise RuntimeError("PS_APIGATEWAY_SIGNING_KEY_PEM is not configured")
    private_key = serialization.load_pem_private_key(
        settings.signing_key_pem.encode("utf-8"), password=None
    )
    public_key_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return SigningKey(
        kid=settings.signing_kid,
        public_key_pem=public_key_pem,
        private_key_pem=settings.signing_key_pem,
    )


def load_previous_public_keys(settings: Settings) -> list[SigningKey]:
    if not settings.previous_public_keys:
        return []
    raw = json.loads(settings.previous_public_keys)
    return [
        SigningKey(kid=item["kid"], public_key_pem=item["public_key_pem"])
        for item in raw
    ]


def _jwk_for_public_pem(kid: str, public_key_pem: str) -> dict:
    public_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
    if not isinstance(public_key, RSAPublicKey):
        raise TypeError(
            f"signing key {kid} is not an RSA key (only RS256 is supported)"
        )
    jwk: dict = json.loads(RSAAlgorithm(RSAAlgorithm.SHA256).to_jwk(public_key))
    jwk["kid"] = kid
    jwk["alg"] = "RS256"
    jwk["use"] = "sig"
    return jwk


def build_jwks_document(settings: Settings) -> dict:
    """Public keys only (current + previous) - spec.md section 2 `/.well-known/jwks.json`."""
    current = load_current_signing_key(settings)
    keys = [_jwk_for_public_pem(current.kid, current.public_key_pem)]
    for prev in load_previous_public_keys(settings):
        keys.append(_jwk_for_public_pem(prev.kid, prev.public_key_pem))
    return {"keys": keys}
