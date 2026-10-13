"""Unit tests for app/clients.py's classify_triage response parsing (no DB, no network --
httpx calls are never actually made; these tests exercise only the pure parsing/heuristic
logic by calling the private helpers' equivalent behaviour via monkeypatched httpx).
"""

from __future__ import annotations

from typing import Self
from uuid import uuid4

import httpx
import pytest

from app import clients
from app.domain.states import CaseKind


class _FakeResponse:
    def __init__(self, status_code: int, body: dict | None) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> dict:
        if self._body is None:
            raise ValueError("no body")
        return self._body


class _FakeAsyncClient:
    def __init__(self, response: _FakeResponse | Exception) -> None:
        self._response = response

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def post(self, *args: object, **kwargs: object) -> _FakeResponse:
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _patch_client(
    monkeypatch: pytest.MonkeyPatch, response: _FakeResponse | Exception
) -> None:
    monkeypatch.setattr(clients.settings, "triage_ai_url", "http://triage-ai.test")
    monkeypatch.setattr(clients, "_client", lambda *a, **k: _FakeAsyncClient(response))
    monkeypatch.setattr(clients, "mint_outbound_token", lambda audience: None)


async def _call(**overrides: object):
    kwargs: dict[str, object] = {
        "case_id": uuid4(),
        "trace_id": "trace-1",
        "origin": "buyer_report",
        "buyer_text": "it never arrived",
        "timeline": [],
        "order": {
            "order_ref": "order-1",
            "order_date": "2026-01-01",
            "promised_by": None,
            "demo_now": "2026-01-10T00:00:00+00:00",
            "state": "CAPTURED",
            "item_titles": [],
            "amount_minor": 1000,
            "currency": "USD",
        },
    }
    kwargs.update(overrides)
    return await clients.classify_triage(**kwargs)  # type: ignore[arg-type]


async def test_classify_triage_happy_path_maps_category_and_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = {
        "triage_id": str(uuid4()),
        "category": "LATE",
        "confidence": 0.92,
        "route": "PROCEED",
        "reasons": ["carrier shows in transit, past promised date"],
        "timeline_flags": [],
        "provenance": {
            "source": "rules",
            "prompt_version": "v1",
            "latency_ms": 5,
        },
    }
    _patch_client(monkeypatch, _FakeResponse(200, body))

    result = await _call()

    assert result is not None
    assert result.category == CaseKind.LATE
    assert result.route == "PROCEED"
    assert result.confidence == pytest.approx(0.92)
    assert result.injection_suspected is False


async def test_classify_triage_human_review_route_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = {
        "triage_id": str(uuid4()),
        "category": "OTHER",
        "confidence": 0.4,
        "route": "HUMAN_REVIEW",
        "reasons": ["low confidence"],
        "timeline_flags": [],
        "provenance": {"source": "model", "prompt_version": "v1", "latency_ms": 5},
    }
    _patch_client(monkeypatch, _FakeResponse(200, body))

    result = await _call()

    assert result is not None
    assert result.route == "HUMAN_REVIEW"
    assert result.category == CaseKind.OTHER


async def test_classify_triage_injection_heuristic_from_reasons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = {
        "triage_id": str(uuid4()),
        "category": "OTHER",
        "confidence": 0.5,
        "route": "HUMAN_REVIEW",
        "reasons": ["possible prompt injection detected in buyer_text"],
        "timeline_flags": [],
        "provenance": {"source": "model", "prompt_version": "v1", "latency_ms": 5},
    }
    _patch_client(monkeypatch, _FakeResponse(200, body))

    result = await _call()

    assert result is not None
    assert result.injection_suspected is True


async def test_classify_triage_injection_heuristic_from_warn_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = {
        "triage_id": str(uuid4()),
        "category": "LATE",
        "confidence": 0.8,
        "route": "PROCEED",
        "reasons": [],
        "timeline_flags": [
            {
                "code": "TIMELINE_GAP",
                "severity": "WARN",
                "origin": "rule",
                "event_ids": [],
                "explanation": "gap in carrier events",
            }
        ],
        "provenance": {"source": "rules", "prompt_version": "v1", "latency_ms": 5},
    }
    _patch_client(monkeypatch, _FakeResponse(200, body))

    result = await _call()

    assert result is not None
    assert result.injection_suspected is True


async def test_classify_triage_non_200_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_client(monkeypatch, _FakeResponse(500, None))
    assert await _call() is None


async def test_classify_triage_malformed_json_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_client(monkeypatch, _FakeResponse(200, None))
    assert await _call() is None


async def test_classify_triage_missing_category_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = {
        "triage_id": str(uuid4()),
        "category": None,
        "confidence": 0.9,
        "route": "PROCEED",
        "reasons": [],
        "timeline_flags": [],
        "provenance": {"source": "rules", "prompt_version": "v1", "latency_ms": 5},
    }
    _patch_client(monkeypatch, _FakeResponse(200, body))
    assert await _call() is None


async def test_classify_triage_connection_error_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_client(monkeypatch, httpx.ConnectError("boom"))
    assert await _call() is None


async def test_classify_triage_no_url_configured_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(clients.settings, "triage_ai_url", "")
    assert await _call() is None
