"""Internal-JWT hardening: `verify_internal_jwt` (app/deps.py) now requires `exp` and
`iss` claims and checks `iss == "api-gateway"` -- previously neither was checked, so a
token missing `exp` entirely never expired, and any signer trusted for ANY issuer value
(or none at all) was accepted."""

from __future__ import annotations

import time
import uuid

import jwt
import pytest


def _raw_token(pg_env, claims: dict) -> str:
    return jwt.encode(
        claims,
        pg_env["private_pem"],
        algorithm="RS256",
        headers={"kid": pg_env["key_id"]},
    )


@pytest.mark.asyncio
async def test_token_without_exp_is_rejected(client, pg_env):
    now = int(time.time())
    token = _raw_token(
        pg_env,
        {
            "iss": "api-gateway",
            "sub": "buyer-1",
            "aud": "mandate",
            "role": "buyer",
            "jti": str(uuid.uuid4()),
            "scope": [],
            "act": {"role": "buyer", "actor_id": "buyer-1"},
            "iat": now,
            # no "exp" -- previously meant "never expires"
        },
    )
    resp = await client.get("/mandates", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_token_with_wrong_issuer_is_rejected(client, pg_env):
    now = int(time.time())
    token = _raw_token(
        pg_env,
        {
            "iss": "some-other-issuer",
            "sub": "buyer-1",
            "aud": "mandate",
            "role": "buyer",
            "jti": str(uuid.uuid4()),
            "scope": [],
            "act": {"role": "buyer", "actor_id": "buyer-1"},
            "iat": now,
            "exp": now + 300,
        },
    )
    resp = await client.get("/mandates", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_token_with_correct_issuer_and_exp_is_accepted(client, buyer_token):
    token = buyer_token()
    resp = await client.get("/mandates", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code != 401
