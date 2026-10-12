"""Unit tests for clients.get_order / clients.capture_order against paypal-adapter's real
envelope shape (services/paypal-adapter/app/ops.py's `_envelope`), per sprint-plan S2-01:
checkout must parse the adapter's actual {ok, status, data, error, ...} response, not an
earlier placeholder shape.
"""

from __future__ import annotations

import httpx
import pytest

from app import clients
from app.settings import Settings


def _settings() -> Settings:
    return Settings(paypal_adapter_base_url="http://adapter.test")


def _fake_client(handler):
    def fake_build_client(base_url, timeout=None):
        return httpx.AsyncClient(
            base_url=base_url, transport=httpx.MockTransport(handler)
        )

    return fake_build_client


@pytest.mark.asyncio
async def test_get_order_ok_unwraps_data(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "ok": True,
                "status": "OK",
                "paypal_http_status": 200,
                "data": {
                    "order_id": "PAY-1",
                    "status": "APPROVED",
                    "custom_id": "mandate-1",
                    "invoice_id": "order-1",
                    "amount_minor": 500,
                    "currency": "USD",
                    "capture_ids": [],
                },
                "error": None,
                "replayed": False,
                "trace_id": "t1",
            },
        )

    monkeypatch.setattr(clients, "build_client", _fake_client(handler))
    result = await clients.get_order(_settings(), "tok", "PAY-1")
    assert result.ok is True
    assert result.definite is True
    assert result.body is not None
    assert result.body["status"] == "APPROVED"
    assert result.body["custom_id"] == "mandate-1"


@pytest.mark.asyncio
async def test_get_order_404_is_definite_failure(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "ok": False,
                "status": "REJECTED",
                "paypal_http_status": None,
                "data": None,
                "error": {
                    "code": "NOT_FOUND",
                    "message": "order not found",
                    "retryable": False,
                },
                "replayed": False,
                "trace_id": "t1",
            },
        )

    monkeypatch.setattr(clients, "build_client", _fake_client(handler))
    result = await clients.get_order(_settings(), "tok", "PAY-missing")
    assert result.ok is False
    assert result.definite is True
    assert result.code == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_order_timeout_is_not_definite(monkeypatch) -> None:
    """A timeout must be reconcilable, not a hard failure -- CAPTURE_UNKNOWN territory,
    never CAPTURE_FAILED, per spec.md section 10."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(clients, "build_client", _fake_client(handler))
    result = await clients.get_order(_settings(), "tok", "PAY-1")
    assert result.ok is False
    assert result.definite is False


@pytest.mark.asyncio
async def test_capture_order_completed_unwraps_capture_status(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("X-Authorization-Ticket") == "ticket-1"
        return httpx.Response(
            201,
            json={
                "ok": True,
                "status": "OK",
                "paypal_http_status": 201,
                "data": {
                    "order_id": "PAY-1",
                    "status": "COMPLETED",
                    "capture_id": "CAP-1",
                    "capture_status": "COMPLETED",
                    "custom_id": "mandate-1",
                    "invoice_id": "order-1",
                    "amount_minor": 500,
                    "currency": "USD",
                },
                "error": None,
                "replayed": False,
                "trace_id": "t1",
            },
        )

    monkeypatch.setattr(clients, "build_client", _fake_client(handler))
    result = await clients.capture_order(
        _settings(),
        "tok",
        paypal_order_id="PAY-1",
        request_id="req-1",
        mandate_id="mandate-1",
        proposal_hash="hash-1",
        amount_minor=500,
        currency="USD",
        ticket="ticket-1",
    )
    assert result.ok is True
    assert result.body is not None
    assert result.body["capture_status"] == "COMPLETED"
    assert result.body["capture_id"] == "CAP-1"


@pytest.mark.asyncio
async def test_capture_order_not_approved_409_is_not_definite(monkeypatch) -> None:
    """ORDER_NOT_APPROVED (adapter's own pre-capture check failing, e.g. a race) must
    never be treated as a definite failure -- no double-capture risk, reconcile sorts
    it out via get_order."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={
                "ok": False,
                "status": "REJECTED",
                "paypal_http_status": None,
                "data": None,
                "error": {
                    "code": "ORDER_NOT_APPROVED",
                    "message": "order is not in APPROVED status",
                    "retryable": False,
                },
                "replayed": False,
                "trace_id": "t1",
            },
        )

    monkeypatch.setattr(clients, "build_client", _fake_client(handler))
    result = await clients.capture_order(
        _settings(),
        "tok",
        paypal_order_id="PAY-1",
        request_id="req-1",
        mandate_id="mandate-1",
        proposal_hash="hash-1",
        amount_minor=500,
        currency="USD",
        ticket="ticket-1",
    )
    assert result.ok is False
    assert result.definite is False
    assert result.detail == "not_approved"


@pytest.mark.asyncio
async def test_capture_order_authorization_mismatch_403_is_definite(
    monkeypatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "ok": False,
                "status": "REJECTED",
                "paypal_http_status": None,
                "data": None,
                "error": {
                    "code": "AUTHORIZATION_MISMATCH",
                    "message": "mandate_id does not match order custom_id",
                    "retryable": False,
                },
                "replayed": False,
                "trace_id": "t1",
            },
        )

    monkeypatch.setattr(clients, "build_client", _fake_client(handler))
    result = await clients.capture_order(
        _settings(),
        "tok",
        paypal_order_id="PAY-1",
        request_id="req-1",
        mandate_id="mandate-1",
        proposal_hash="hash-1",
        amount_minor=500,
        currency="USD",
        ticket="ticket-1",
    )
    assert result.ok is False
    assert result.definite is True
    assert result.code == "AUTHORIZATION_MISMATCH"


@pytest.mark.asyncio
async def test_capture_order_timeout_is_capture_unknown_territory(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(clients, "build_client", _fake_client(handler))
    result = await clients.capture_order(
        _settings(),
        "tok",
        paypal_order_id="PAY-1",
        request_id="req-1",
        mandate_id="mandate-1",
        proposal_hash="hash-1",
        amount_minor=500,
        currency="USD",
        ticket="ticket-1",
    )
    assert result.ok is False
    assert result.definite is False
