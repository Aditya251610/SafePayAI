"""JWT minting, JWKS document, rotation, and deny-by-default (task TESTS checklist
items 4 and 5). Pure unit tests - no DB, no running app - using the gateway's own
mint + JWKS-build code and PyJWT as the "downstream verifier" stand-in (every real
service does this via `libs/common.auth.jwt`, pointed at this gateway's JWKS)."""

from __future__ import annotations

import time

import jwt
import pytest
from jwt.algorithms import RSAAlgorithm

from app.deps import Principal
from app.settings import get_settings
from app.tokens.keys import (
    build_jwks_document,
    load_current_signing_key,
    load_previous_public_keys,
)
from app.tokens.mint import mint_for_upstream


def _principal(role: str = "buyer") -> Principal:
    return Principal(
        actor_type=role,
        actor_id="user-1",
        role=role,
        epoch=0,
        sid_hash="deadbeef",
        display_name=None,
    )


def _jwk_lookup(jwks_doc: dict, kid: str):
    for jwk in jwks_doc["keys"]:
        if jwk["kid"] == kid:
            return RSAAlgorithm(RSAAlgorithm.SHA256).from_jwk(jwk)
    return None


# --- minting shape -----------------------------------------------------------


def test_mint_claims_match_spec_shape():
    settings = get_settings()
    token = mint_for_upstream(
        _principal(), audience="catalog", request_id="req-1", scope=["catalog:read"]
    )
    header = jwt.get_unverified_header(token)
    assert header["alg"] == "RS256"
    assert header["kid"] == settings.signing_kid

    jwks_doc = build_jwks_document(settings)
    key = _jwk_lookup(jwks_doc, header["kid"])
    claims = jwt.decode(token, key=key, algorithms=["RS256"], audience="catalog")

    assert claims["iss"] == "api-gateway"
    assert claims["sub"] == "user-1"
    assert claims["aud"] == "catalog"
    assert claims["role"] == "buyer"
    assert claims["act"]["actor_id"] == "user-1"
    assert claims["act"]["auth_method"] == "session"
    assert claims["sid"] == "deadbeef"
    assert claims["req"] == "req-1"
    assert claims["scope"] == ["catalog:read"]
    assert "jti" in claims and "iat" in claims and "exp" in claims


def test_mint_ttl_clamped_to_120s_hard_max(monkeypatch):
    monkeypatch.setenv("PS_APIGATEWAY_INTERNAL_TOKEN_TTL_S", "99999")
    token = mint_for_upstream(_principal(), audience="catalog", request_id="r")
    claims = jwt.decode(token, options={"verify_signature": False})
    assert claims["exp"] - claims["iat"] <= 120


def test_mint_jti_unique_per_call():
    seen = set()
    for _ in range(50):
        token = mint_for_upstream(_principal(), audience="catalog", request_id="r")
        claims = jwt.decode(token, options={"verify_signature": False})
        assert claims["jti"] not in seen
        seen.add(claims["jti"])


def test_mint_never_reuses_token_across_audiences():
    t1 = mint_for_upstream(_principal(), audience="catalog", request_id="r1")
    t2 = mint_for_upstream(_principal(), audience="mandate", request_id="r2")
    c1 = jwt.decode(t1, options={"verify_signature": False})
    c2 = jwt.decode(t2, options={"verify_signature": False})
    assert c1["aud"] != c2["aud"]
    assert c1["jti"] != c2["jti"]


# --- deny-by-default ----------------------------------------------------------


def test_deny_wrong_audience():
    settings = get_settings()
    token = mint_for_upstream(_principal(), audience="catalog", request_id="r")
    header = jwt.get_unverified_header(token)
    key = _jwk_lookup(build_jwks_document(settings), header["kid"])
    with pytest.raises(jwt.InvalidAudienceError):
        jwt.decode(token, key=key, algorithms=["RS256"], audience="mandate")


def test_deny_expired_token():
    settings = get_settings()
    signing_key = load_current_signing_key(settings)
    now = int(time.time())
    claims = {
        "iss": "api-gateway",
        "sub": "u",
        "aud": "catalog",
        "iat": now - 120,
        "exp": now - 60,
        "jti": "x",
        "req": "r",
        "act": {},
        "role": "buyer",
        "scope": [],
        "sid": None,
    }
    token = jwt.encode(
        claims,
        signing_key.private_key_pem,
        algorithm="RS256",
        headers={"kid": signing_key.kid},
    )
    key = _jwk_lookup(build_jwks_document(settings), signing_key.kid)
    with pytest.raises(jwt.ExpiredSignatureError):
        jwt.decode(token, key=key, algorithms=["RS256"], audience="catalog")


def test_deny_no_token():
    """A verifier given no token at all must reject - the production route
    dependency (`app.deps.require_session`) demonstrates the same fail-closed
    behaviour for the gateway's own cookie session; see tests/integration/test_roles.py."""
    with pytest.raises(jwt.exceptions.DecodeError):
        jwt.decode("", options={"verify_signature": False})


def test_deny_alg_none_switch():
    settings = get_settings()
    signing_key = load_current_signing_key(settings)
    now = int(time.time())
    forged_claims = {
        "iss": "api-gateway",
        "sub": "u",
        "aud": "catalog",
        "iat": now,
        "exp": now + 60,
    }
    forged = jwt.encode(forged_claims, key="", algorithm="none")
    key = _jwk_lookup(build_jwks_document(settings), signing_key.kid)
    with pytest.raises((jwt.InvalidAlgorithmError, jwt.DecodeError)):
        jwt.decode(forged, key=key, algorithms=["RS256"], audience="catalog")


def test_deny_unknown_kid_fails_closed():
    jwks_doc = build_jwks_document(get_settings())
    assert _jwk_lookup(jwks_doc, "unknown-kid-should-not-exist") is None


class _ReplayCache:
    """Minimal stand-in for the downstream `jti` replay cache that
    architecture/auth-gateway.md section 3.1 assigns to each VERIFIER (not the
    gateway, which only mints - see tokens/mint.py's module docstring). Test-only;
    not production code."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def check_and_record(self, jti: str) -> bool:
        if jti in self._seen:
            return False
        self._seen.add(jti)
        return True


def test_deny_replayed_jti_via_downstream_replay_cache():
    cache = _ReplayCache()
    token = mint_for_upstream(
        _principal(), audience="checkout", request_id="r1", scope=["checkout:capture"]
    )
    claims = jwt.decode(token, options={"verify_signature": False})
    assert cache.check_and_record(claims["jti"]) is True
    assert cache.check_and_record(claims["jti"]) is False


# --- JWKS rotation -------------------------------------------------------------


def test_jwks_contains_current_and_previous_kid(rsa_keypairs):
    jwks_doc = build_jwks_document(get_settings())
    kids = {k["kid"] for k in jwks_doc["keys"]}
    assert rsa_keypairs["current"]["kid"] in kids
    assert rsa_keypairs["previous"]["kid"] in kids


def test_token_signed_with_previous_kid_still_verifies_during_overlap(rsa_keypairs):
    settings = get_settings()
    prev = rsa_keypairs["previous"]
    now = int(time.time())
    claims = {
        "iss": "api-gateway",
        "sub": "u",
        "aud": "catalog",
        "iat": now,
        "exp": now + 60,
        "jti": "y",
        "req": "r",
        "act": {},
        "role": "buyer",
        "scope": [],
        "sid": None,
    }
    token = jwt.encode(
        claims, prev["private_pem"], algorithm="RS256", headers={"kid": prev["kid"]}
    )
    key = _jwk_lookup(build_jwks_document(settings), prev["kid"])
    assert key is not None
    out = jwt.decode(token, key=key, algorithms=["RS256"], audience="catalog")
    assert out["aud"] == "catalog"


def test_retired_previous_key_is_rejected(monkeypatch, rsa_keypairs):
    """After the previous key is retired (removed from
    PS_APIGATEWAY_PREVIOUS_PUBLIC_KEYS), a token still bearing its kid can no
    longer be verified from the published JWKS - it fails closed (no key found)."""
    monkeypatch.setenv("PS_APIGATEWAY_PREVIOUS_PUBLIC_KEYS", "[]")
    settings = get_settings()
    assert load_previous_public_keys(settings) == []
    jwks_doc = build_jwks_document(settings)
    assert _jwk_lookup(jwks_doc, rsa_keypairs["previous"]["kid"]) is None
