"""Unit tests for app/clients.py's get_mandate_terms: a revoked/expired/exhausted mandate
must yield (None, None, False) -- same fail-closed shape as "unreachable" -- so a NEW case
opened after revocation gets no protection (api.md s6, confirmed D1: "mandate.revoked
blocks pre-authorization for cases not yet opened; opened cases keep their terms
snapshot"). No DB, no real network -- httpx is monkeypatched the same way
test_triage_client.py does it.
"""

from __future__ import annotations

from typing import Self

import pytest

from app_resolution import clients


class _FakeResponse:
    def __init__(self, status_code: int, body: dict | None) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> dict:
        if self._body is None:
            raise ValueError("no body")
        return self._body


class _FakeAsyncClient:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def get(self, *args: object, **kwargs: object) -> _FakeResponse:
        return self._response


def _patch_client(monkeypatch: pytest.MonkeyPatch, body: dict) -> None:
    monkeypatch.setattr(clients.settings, "mandate_url", "http://mandate.test")
    monkeypatch.setattr(
        clients, "_client", lambda *a, **k: _FakeAsyncClient(_FakeResponse(200, body))
    )
    monkeypatch.setattr(clients, "mint_outbound_token", lambda audience: None)


def _terms_body(*, mandate_status: str) -> dict:
    return {
        "mandate_status": mandate_status,
        "integrity": "OK",
        "terms_hash": "abc123",
        "protection": {
            "kinds_covered": ["LATE", "LOST"],
            "max_refund_minor": 5000,
            "deliver_by_days": 14,
        },
    }


@pytest.mark.asyncio
async def test_active_mandate_returns_terms(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(monkeypatch, _terms_body(mandate_status="active"))
    terms, terms_hash, hmac_valid = await clients.get_mandate_terms("m1")
    assert terms is not None
    assert terms.max_refund_minor == 5000
    assert terms_hash == "abc123"
    assert hmac_valid is True


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["revoked", "expired", "exhausted"])
async def test_non_active_mandate_fails_closed(
    monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    _patch_client(monkeypatch, _terms_body(mandate_status=status))
    terms, terms_hash, hmac_valid = await clients.get_mandate_terms("m1")
    assert terms is None
    assert terms_hash is None
    assert hmac_valid is False
