"""Outbound HTTP calls: catalog /prices/resolve, mandate /evaluate + GET /mandates/{id},
paypal-adapter create_order/get_order/capture_order. spec.md section 1: these are the only
downward sync calls checkout makes. Every failure mode here must fail closed per spec.md
section 10 (mandate/catalog down -> BLOCK, never allow).
"""

from __future__ import annotations

from typing import Any

import httpx
from safepayai_common.http.client import build_client

from app.settings import Settings


class UpstreamError(Exception):
    """Raised for any catalog/mandate/adapter failure: timeout, connection error, 5xx,
    or malformed response. Callers map this to a fail-closed BLOCK/CREATE_UNKNOWN."""

    def __init__(self, service: str, detail: str) -> None:
        super().__init__(f"{service}: {detail}")
        self.service = service
        self.detail = detail


async def resolve_prices(
    settings: Settings, token: str, lines: list[dict[str, Any]]
) -> dict[str, Any]:
    timeout = httpx.Timeout(settings.http_timeout_catalog_ms / 1000.0)
    async with build_client(settings.catalog_base_url, timeout=timeout) as client:
        try:
            resp = await client.post(
                "/prices/resolve",
                json={"lines": lines},
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.HTTPError as exc:
            raise UpstreamError("catalog", str(exc)) from exc
    if resp.status_code != 200:
        raise UpstreamError(
            "catalog", f"status={resp.status_code} body={resp.text[:200]}"
        )
    try:
        return dict(resp.json())
    except ValueError as exc:
        raise UpstreamError("catalog", "malformed JSON response") from exc


async def evaluate_mandate(
    settings: Settings, token: str, mandate_id: str, cart: dict[str, Any]
) -> dict[str, Any]:
    timeout = httpx.Timeout(settings.http_timeout_mandate_ms / 1000.0)
    async with build_client(settings.mandate_base_url, timeout=timeout) as client:
        try:
            resp = await client.post(
                f"/mandates/{mandate_id}/evaluate",
                json={"cart": cart},
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.HTTPError as exc:
            raise UpstreamError("mandate", str(exc)) from exc
    if resp.status_code != 200:
        raise UpstreamError(
            "mandate", f"status={resp.status_code} body={resp.text[:200]}"
        )
    try:
        return dict(resp.json())
    except ValueError as exc:
        raise UpstreamError("mandate", "malformed JSON response") from exc


async def get_mandate(
    settings: Settings, token: str, mandate_id: str
) -> dict[str, Any]:
    timeout = httpx.Timeout(settings.http_timeout_mandate_ms / 1000.0)
    async with build_client(settings.mandate_base_url, timeout=timeout) as client:
        try:
            resp = await client.get(
                f"/mandates/{mandate_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.HTTPError as exc:
            raise UpstreamError("mandate", str(exc)) from exc
    if resp.status_code == 404:
        raise UpstreamError("mandate", "mandate not found")
    if resp.status_code != 200:
        raise UpstreamError(
            "mandate", f"status={resp.status_code} body={resp.text[:200]}"
        )
    try:
        return dict(resp.json())
    except ValueError as exc:
        raise UpstreamError("mandate", "malformed JSON response") from exc


class AdapterResult:
    """Outcome of an adapter call. `definite` distinguishes a clean 4xx failure
    (CREATE_FAILED) from timeout/5xx/409/unknown-shape (CREATE_UNKNOWN), per spec.md
    section 10's failure-mode table."""

    def __init__(
        self, ok: bool, definite: bool, body: dict[str, Any] | None, detail: str
    ) -> None:
        self.ok = ok
        self.definite = definite
        self.body = body
        self.detail = detail


async def create_order(
    settings: Settings,
    token: str,
    *,
    idempotency_key: str,
    amount_minor: int,
    currency: str,
    custom_id: str,
    invoice_id: str,
    return_url: str,
    cancel_url: str,
    ticket: str,
) -> AdapterResult:
    timeout = httpx.Timeout(settings.http_timeout_adapter_ms / 1000.0)
    payload = {
        "idempotency_key": idempotency_key,
        "ticket": ticket,
        "amount_minor": amount_minor,
        "currency": currency,
        "custom_id": custom_id,
        "invoice_id": invoice_id,
        "return_url": return_url,
        "cancel_url": cancel_url,
    }
    async with build_client(
        settings.paypal_adapter_base_url, timeout=timeout
    ) as client:
        try:
            resp = await client.post(
                "/v1/orders",
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "PayPal-Request-Id": idempotency_key,
                },
            )
        except httpx.TimeoutException as exc:
            return AdapterResult(False, False, None, f"timeout: {exc}")
        except httpx.HTTPError as exc:
            return AdapterResult(False, False, None, f"connection_error: {exc}")

    if resp.status_code in (200, 201):
        try:
            return AdapterResult(True, True, resp.json(), "created")
        except ValueError:
            return AdapterResult(False, False, None, "malformed JSON response")
    if resp.status_code == 409:
        return AdapterResult(False, False, None, "conflict, treat as unknown")
    if 400 <= resp.status_code < 500 and resp.status_code != 409:
        return AdapterResult(
            False, True, None, f"definite failure status={resp.status_code}"
        )
    return AdapterResult(False, False, None, f"status={resp.status_code}")


async def get_order(
    settings: Settings, token: str, paypal_order_id: str
) -> AdapterResult:
    timeout = httpx.Timeout(settings.http_timeout_adapter_ms / 1000.0)
    async with build_client(
        settings.paypal_adapter_base_url, timeout=timeout
    ) as client:
        try:
            resp = await client.get(
                f"/v1/orders/{paypal_order_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.HTTPError as exc:
            return AdapterResult(False, False, None, f"connection_error: {exc}")
    if resp.status_code == 200:
        try:
            return AdapterResult(True, True, resp.json(), "ok")
        except ValueError:
            return AdapterResult(False, False, None, "malformed JSON response")
    if 400 <= resp.status_code < 500:
        return AdapterResult(
            False, True, None, f"definite failure status={resp.status_code}"
        )
    return AdapterResult(False, False, None, f"status={resp.status_code}")


async def capture_order(
    settings: Settings,
    token: str,
    *,
    paypal_order_id: str,
    idempotency_key: str,
    ticket: str,
) -> AdapterResult:
    timeout = httpx.Timeout(settings.http_timeout_adapter_ms / 1000.0)
    async with build_client(
        settings.paypal_adapter_base_url, timeout=timeout
    ) as client:
        try:
            resp = await client.post(
                f"/v1/orders/{paypal_order_id}/capture",
                json={"idempotency_key": idempotency_key, "ticket": ticket},
                headers={
                    "Authorization": f"Bearer {token}",
                    "PayPal-Request-Id": idempotency_key,
                },
            )
        except httpx.TimeoutException as exc:
            return AdapterResult(False, False, None, f"timeout: {exc}")
        except httpx.HTTPError as exc:
            return AdapterResult(False, False, None, f"connection_error: {exc}")
    if resp.status_code in (200, 201):
        try:
            return AdapterResult(True, True, resp.json(), "captured")
        except ValueError:
            return AdapterResult(False, False, None, "malformed JSON response")
    if resp.status_code == 409:
        return AdapterResult(False, False, None, "conflict, treat as unknown")
    if 400 <= resp.status_code < 500 and resp.status_code != 409:
        return AdapterResult(
            False, True, None, f"definite failure status={resp.status_code}"
        )
    return AdapterResult(False, False, None, f"status={resp.status_code}")
