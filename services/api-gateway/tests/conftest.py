"""Root fixtures shared by unit and integration tests: RSA signing keys + settings
env vars. No DB access here - unit tests must run without a Postgres instance
(matches .github/workflows/ci-python-service.yml's `unit` job, which has no
postgres service container; only the `integration` job does).
"""

from __future__ import annotations

import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def _generate_rsa_pem_pair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_pem, public_pem


@pytest.fixture(scope="session")
def rsa_keypairs():
    """Two keypairs: 'current' (k1) and 'previous' (k0), for rotation tests."""
    current_private, current_public = _generate_rsa_pem_pair()
    previous_private, previous_public = _generate_rsa_pem_pair()
    return {
        "current": {"kid": "k1", "private_pem": current_private, "public_pem": current_public},
        "previous": {"kid": "k0", "private_pem": previous_private, "public_pem": previous_public},
    }


@pytest.fixture(autouse=True)
def _env(monkeypatch, rsa_keypairs):
    monkeypatch.setenv("PS_APIGATEWAY_SIGNING_KEY_PEM", rsa_keypairs["current"]["private_pem"])
    monkeypatch.setenv("PS_APIGATEWAY_SIGNING_KID", rsa_keypairs["current"]["kid"])
    monkeypatch.setenv(
        "PS_APIGATEWAY_PREVIOUS_PUBLIC_KEYS",
        json.dumps(
            [
                {
                    "kid": rsa_keypairs["previous"]["kid"],
                    "public_key_pem": rsa_keypairs["previous"]["public_pem"],
                }
            ]
        ),
    )
    monkeypatch.setenv("PS_APIGATEWAY_INTERNAL_TOKEN_TTL_S", "60")
    monkeypatch.setenv("PS_APIGATEWAY_MAX_EPHEMERAL_BUYERS", "500")
    monkeypatch.setenv("PS_APIGATEWAY_SESSION_TTL_BUYER_S", "7200")
    monkeypatch.setenv("PS_APIGATEWAY_SESSION_CAP_BUYER_S", "28800")
    monkeypatch.setenv("PS_APIGATEWAY_SESSION_TTL_STAFF_S", "3600")
    monkeypatch.setenv("PS_APIGATEWAY_TICK_SECRET", "test-tick-secret")
    monkeypatch.setenv("PS_APIGATEWAY_DEMO_MODE", "true")

    from app.ratelimit import limiter

    limiter.reset()

    yield

    limiter.reset()
