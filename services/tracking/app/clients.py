"""Outbound sync calls: checkout (order facts, fallback for capture_id/mandate_id/protected_until)
and paypal-adapter (add/cancel tracker - best-effort signal only, spec s1, s7).

Mirrors services/checkout/app/clients.py's Result-object pattern. Every function here fails
closed/soft per spec.md section 1 and section 7: checkout unreachable blocks shipment creation
(503, nothing created); paypal-adapter failure is NEVER an error (paypal_sync=FAILED, retried
on ticks, never blocks shipment creation).

Known gap (flagged, not a tracking bug): checkout's current `GET /orders/{id}` response
(services/checkout/app/routers/orders.py `_order_view`) does not yet expose `capture_id` or a
demo `protected_until` window; this falls back to `paypal_order_id` as capture_id and a locally
configured default window when those fields are absent, rather than guessing a wrong contract.
paypal-adapter's tracker endpoints (services/paypal-adapter/app/routers/tracking.py) are
themselves still 501 stubs at the time of writing, so add/cancel tracker calls will surface as
failures until that service implements them - exactly the non-blocking failure mode spec s1/s7
already require.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.settings import settings

DEFAULT_PROTECTION_WINDOW_DAYS = (
    14  # (I) used only when checkout doesn't expose protected_until
)


class OrderFacts:
    def __init__(
        self,
        order_id: str,
        status: str,
        capture_id: str,
        mandate_id: str,
        protected_until: datetime | None,
    ) -> None:
        self.order_id = order_id
        self.status = status
        self.capture_id = capture_id
        self.mandate_id = mandate_id
        self.protected_until = protected_until


def _client(base_url: str, timeout_s: float = 5.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=base_url, timeout=httpx.Timeout(timeout_s))


async def get_order_facts(order_id: str, token: str | None = None) -> OrderFacts | None:
    """GET /orders/{order_id} on checkout. None = unreachable (caller fails closed, 503)."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        async with _client(settings.checkout_url) as client:
            resp = await client.get(f"/orders/{order_id}", headers=headers)
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    try:
        body = resp.json()
    except ValueError:
        return None

    mandate_id = body.get("mandate_id")
    capture_id = body.get("capture_id") or body.get("paypal_order_id")
    status = body.get("status", "")
    protected_until_raw = body.get("protected_until")
    protected_until = None
    if protected_until_raw:
        try:
            protected_until = datetime.fromisoformat(protected_until_raw)
        except ValueError:
            protected_until = None
    return OrderFacts(
        order_id=order_id,
        status=str(status),
        capture_id=str(capture_id) if capture_id else "",
        mandate_id=str(mandate_id) if mandate_id else "",
        protected_until=protected_until,
    )


class AdapterResult:
    def __init__(
        self,
        ok: bool,
        status_code: int | None,
        body: dict[str, Any] | None,
        detail: str,
    ) -> None:
        self.ok = ok
        self.status_code = status_code
        self.body = body
        self.detail = detail


async def add_tracking(
    *,
    order_id: str,
    capture_id: str,
    tracking_number: str,
    carrier_name: str,
    token: str | None = None,
) -> AdapterResult:
    """POST /orders/{order_id}/track on paypal-adapter (spec s1: tracker id =
    {capture_id}-{tracking_number}; best-effort signal, never blocks shipment creation)."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    payload = {
        "capture_id": capture_id,
        "tracking_number": tracking_number,
        "carrier": carrier_name,
    }
    try:
        async with _client(settings.paypal_adapter_url) as client:
            resp = await client.post(
                f"/orders/{order_id}/track", json=payload, headers=headers
            )
    except httpx.HTTPError as exc:
        return AdapterResult(False, None, None, f"connection_error: {exc}")
    try:
        body = resp.json() if resp.content else None
    except ValueError:
        body = None
    return AdapterResult(
        resp.status_code == 201, resp.status_code, body, f"status={resp.status_code}"
    )


async def cancel_tracking(
    *, order_id: str, tracker_id: str, token: str | None = None
) -> AdapterResult:
    """Best-effort PATCH to CANCELLED on paypal-adapter (spec s1: irreversible once applied)."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        async with _client(settings.paypal_adapter_url) as client:
            resp = await client.patch(
                f"/orders/{order_id}/trackers/{tracker_id}/status",
                json={"status": "CANCELLED"},
                headers=headers,
            )
    except httpx.HTTPError as exc:
        return AdapterResult(False, None, None, f"connection_error: {exc}")
    return AdapterResult(
        resp.status_code == 204, resp.status_code, None, f"status={resp.status_code}"
    )
