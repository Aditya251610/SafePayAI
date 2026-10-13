"""L1 unit tests for app.ops.get_capture / add_tracking / get_tracking: envelope shapes,
PayPal-error-to-OpError mapping, the tracker_id composite-key helper, and the natural-key
duplicate-add fallback -- using a fake PayPalClient (no network)."""

from __future__ import annotations

from typing import Any

import pytest

from app import ops
from app.paypal_client import PayPalAuthError, PayPalUpstreamError


class _FakeClient:
    def __init__(self, **handlers: Any) -> None:
        self._handlers = handlers

    async def get_capture(self, capture_id: str) -> dict[str, Any]:
        return await self._call("get_capture", capture_id)

    async def add_tracker(self, order_id: str, **kwargs: Any) -> dict[str, Any]:
        return await self._call("add_tracker", order_id, **kwargs)

    async def get_tracker(self, order_id: str, tracker_id: str) -> dict[str, Any]:
        return await self._call("get_tracker", order_id, tracker_id)

    async def _call(self, name: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        handler = self._handlers[name]
        result = handler(*args, **kwargs)
        if isinstance(result, Exception):
            raise result
        return result


def test_tracker_id_is_capture_id_dash_tracking_number():
    assert ops._tracker_id("CAP1", "TRACK1") == "CAP1-TRACK1"


@pytest.mark.asyncio
async def test_get_capture_envelope_shape():
    client = _FakeClient(
        get_capture=lambda capture_id: {
            "id": capture_id,
            "status": "COMPLETED",
            "amount": {"currency_code": "USD", "value": "15.00"},
            "invoice_id": "ord_1",
            "custom_id": "mdt_1",
            "final_capture": True,
        }
    )
    envelope = await ops.get_capture(client, "CAP1", trace_id="tr1")
    assert envelope["ok"] is True
    assert envelope["status"] == "OK"
    assert envelope["data"] == {
        "capture_id": "CAP1",
        "status": "COMPLETED",
        "amount_minor": 1500,
        "currency": "USD",
        "invoice_id": "ord_1",
        "custom_id": "mdt_1",
        "final_capture": True,
    }


@pytest.mark.asyncio
async def test_get_capture_404_maps_to_not_found():
    client = _FakeClient(get_capture=lambda capture_id: PayPalUpstreamError("nf", status_code=404))
    with pytest.raises(ops.OpError) as exc_info:
        await ops.get_capture(client, "missing", trace_id="tr1")
    assert exc_info.value.code == "NOT_FOUND"
    assert exc_info.value.http_status == 404


@pytest.mark.asyncio
async def test_get_capture_auth_error_maps_to_upstream_auth_failed():
    client = _FakeClient(get_capture=lambda capture_id: PayPalAuthError("no"))
    with pytest.raises(ops.OpError) as exc_info:
        await ops.get_capture(client, "CAP1", trace_id="tr1")
    assert exc_info.value.code == "UPSTREAM_AUTH_FAILED"
    assert exc_info.value.http_status == 503


@pytest.mark.asyncio
async def test_add_tracking_envelope_shape():
    client = _FakeClient(add_tracker=lambda order_id, **kw: {"trackers": [{"status": "SHIPPED"}]})
    envelope = await ops.add_tracking(
        client,
        "ORDER1",
        capture_id="CAP1",
        tracking_number="TRACK1",
        carrier_name_other="Demo Carrier",
        notify_payer=False,
        trace_id="tr1",
    )
    assert envelope["ok"] is True
    assert envelope["replayed"] is False
    assert envelope["data"] == {
        "order_id": "ORDER1",
        "tracker_id": "CAP1-TRACK1",
        "status": "SHIPPED",
    }


@pytest.mark.asyncio
async def test_add_tracking_duplicate_422_reads_back_and_reports_replayed():
    client = _FakeClient(
        add_tracker=lambda order_id, **kw: PayPalUpstreamError("dup", status_code=422),
        get_tracker=lambda order_id, tracker_id: {"id": tracker_id, "status": "SHIPPED"},
    )
    envelope = await ops.add_tracking(
        client,
        "ORDER1",
        capture_id="CAP1",
        tracking_number="TRACK1",
        carrier_name_other="Demo Carrier",
        notify_payer=False,
        trace_id="tr1",
    )
    assert envelope["ok"] is True
    assert envelope["replayed"] is True
    assert envelope["data"]["tracker_id"] == "CAP1-TRACK1"


@pytest.mark.asyncio
async def test_add_tracking_422_with_failed_readback_propagates_rejection():
    client = _FakeClient(
        add_tracker=lambda order_id, **kw: PayPalUpstreamError("dup", status_code=422),
        get_tracker=lambda order_id, tracker_id: PayPalUpstreamError("nf", status_code=404),
    )
    with pytest.raises(ops.OpError) as exc_info:
        await ops.add_tracking(
            client,
            "ORDER1",
            capture_id="CAP1",
            tracking_number="TRACK1",
            carrier_name_other="Demo Carrier",
            notify_payer=False,
            trace_id="tr1",
        )
    assert exc_info.value.code == "UPSTREAM_REJECTED"
    assert exc_info.value.http_status == 422


@pytest.mark.asyncio
async def test_add_tracking_5xx_maps_to_unknown_retryable():
    client = _FakeClient(
        add_tracker=lambda order_id, **kw: PayPalUpstreamError("boom", status_code=500)
    )
    with pytest.raises(ops.OpError) as exc_info:
        await ops.add_tracking(
            client,
            "ORDER1",
            capture_id="CAP1",
            tracking_number="TRACK1",
            carrier_name_other="Demo Carrier",
            notify_payer=False,
            trace_id="tr1",
        )
    assert exc_info.value.status == "UNKNOWN"
    assert exc_info.value.retryable is True
    assert exc_info.value.http_status == 504


@pytest.mark.asyncio
async def test_get_tracking_always_reports_verified_false_and_null_carrier_status():
    client = _FakeClient(
        get_tracker=lambda order_id, tracker_id: {"id": tracker_id, "status": "SHIPPED"}
    )
    envelope = await ops.get_tracking(client, "ORDER1", "CAP1-TRACK1", trace_id="tr1")
    assert envelope["data"]["verified"] is False
    assert envelope["data"]["carrier_status"] is None
    assert envelope["data"]["paypal_status"] == "SHIPPED"


def test_error_envelope_shape_matches_refund_handlers_inline_dict():
    exc = ops.OpError("REJECTED", "NOT_FOUND", "capture not found", http_status=404)
    envelope = ops.error_envelope(exc, "tr1")
    assert envelope == {
        "ok": False,
        "status": "REJECTED",
        "paypal_http_status": None,
        "data": None,
        "error": {
            "code": "NOT_FOUND",
            "message": "capture not found",
            "retryable": False,
            "paypal_name": None,
        },
        "replayed": False,
        "trace_id": "tr1",
    }
