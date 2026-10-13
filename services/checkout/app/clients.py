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
    settings: Settings,
    token: str,
    mandate_id: str,
    cart: dict[str, Any],
    committed_minor: int | None = None,
) -> dict[str, Any]:
    timeout = httpx.Timeout(settings.http_timeout_mandate_ms / 1000.0)
    async with build_client(settings.mandate_base_url, timeout=timeout) as client:
        try:
            resp = await client.post(
                f"/mandates/{mandate_id}/evaluate",
                json={"cart": cart, "committed_minor": committed_minor},
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
    section 10's failure-mode table. `code` carries the adapter's own error/status code
    (e.g. "ORDER_NOT_APPROVED", "AUTHORIZATION_MISMATCH") when available, so callers can
    branch precisely instead of only on the HTTP status bucket."""

    def __init__(
        self,
        ok: bool,
        definite: bool,
        body: dict[str, Any] | None,
        detail: str,
        code: str | None = None,
    ) -> None:
        self.ok = ok
        self.definite = definite
        self.body = body
        self.detail = detail
        self.code = code


async def create_order(
    settings: Settings,
    token: str,
    *,
    idempotency_key: str,
    mandate_id: str,
    proposal_hash: str,
    internal_order_id: str,
    amount_minor: int,
    currency: str,
    return_url: str,
    cancel_url: str,
    ticket: str,
) -> AdapterResult:
    timeout = httpx.Timeout(settings.http_timeout_adapter_ms / 1000.0)
    payload = {
        "request_id": idempotency_key,
        "mandate_id": mandate_id,
        "proposal_hash": proposal_hash,
        "internal_order_id": internal_order_id,
        "amount_minor": amount_minor,
        "currency": currency,
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
                    "X-Authorization-Ticket": ticket,
                },
            )
        except httpx.TimeoutException as exc:
            return AdapterResult(False, False, None, f"timeout: {exc}")
        except httpx.HTTPError as exc:
            return AdapterResult(False, False, None, f"connection_error: {exc}")

    if resp.status_code in (200, 201):
        try:
            envelope = resp.json()
        except ValueError:
            return AdapterResult(False, False, None, "malformed JSON response")
        if envelope.get("ok"):
            return AdapterResult(True, True, envelope.get("data"), "created")
        error = envelope.get("error") or {}
        return AdapterResult(
            False, True, None, error.get("message", "rejected"), error.get("code")
        )
    if resp.status_code == 409:
        return AdapterResult(False, False, None, "conflict, treat as unknown")
    if 400 <= resp.status_code < 500 and resp.status_code != 409:
        return AdapterResult(
            False, True, None, f"definite failure status={resp.status_code} body={resp.text[:300]}"
        )
    return AdapterResult(False, False, None, f"status={resp.status_code}")


def _parse_envelope(resp: httpx.Response) -> dict[str, Any] | None:
    """paypal-adapter's response shape (ops._envelope): {ok, status, paypal_http_status,
    data, error, replayed, trace_id}. Returns None on malformed JSON."""
    try:
        parsed = resp.json()
    except ValueError:
        return None
    return dict(parsed) if isinstance(parsed, dict) else None


async def get_order(
    settings: Settings, token: str, paypal_order_id: str
) -> AdapterResult:
    """GET /v1/orders/{id} (adapter api.md section 5.2). Used both pre-capture (to
    confirm APPROVED before capturing) and for CAPTURE_UNKNOWN reconciliation (to check
    whether PayPal already shows COMPLETED, so we never call capture twice)."""
    timeout = httpx.Timeout(settings.http_timeout_adapter_ms / 1000.0)
    async with build_client(
        settings.paypal_adapter_base_url, timeout=timeout
    ) as client:
        try:
            resp = await client.get(
                f"/v1/orders/{paypal_order_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.TimeoutException as exc:
            return AdapterResult(False, False, None, f"timeout: {exc}")
        except httpx.HTTPError as exc:
            return AdapterResult(False, False, None, f"connection_error: {exc}")
    envelope = _parse_envelope(resp)
    if envelope is None:
        return AdapterResult(False, False, None, "malformed JSON response")
    if resp.status_code == 200 and envelope.get("ok"):
        return AdapterResult(True, True, envelope.get("data"), "ok")
    error_code = (envelope.get("error") or {}).get("code")
    if resp.status_code in (400, 403, 404, 409, 422):
        return AdapterResult(
            False,
            True,
            None,
            f"definite failure status={resp.status_code}",
            code=error_code,
        )
    return AdapterResult(
        False, False, None, f"status={resp.status_code}", code=error_code
    )


async def capture_order(
    settings: Settings,
    token: str,
    *,
    paypal_order_id: str,
    request_id: str,
    mandate_id: str,
    proposal_hash: str,
    amount_minor: int,
    currency: str,
    ticket: str,
) -> AdapterResult:
    """POST /v1/orders/{id}/capture (adapter api.md section 5.3 / schemas.CaptureOrderRequest).
    Body fields match the adapter's real contract (request_id/mandate_id/proposal_hash/
    amount_minor/currency) -- the ticket travels as the `X-Authorization-Ticket` header,
    not in the body."""
    timeout = httpx.Timeout(settings.http_timeout_adapter_ms / 1000.0)
    async with build_client(
        settings.paypal_adapter_base_url, timeout=timeout
    ) as client:
        try:
            resp = await client.post(
                f"/v1/orders/{paypal_order_id}/capture",
                json={
                    "request_id": request_id,
                    "mandate_id": mandate_id,
                    "proposal_hash": proposal_hash,
                    "amount_minor": amount_minor,
                    "currency": currency,
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Authorization-Ticket": ticket,
                },
            )
        except httpx.TimeoutException as exc:
            return AdapterResult(False, False, None, f"timeout: {exc}")
        except httpx.HTTPError as exc:
            return AdapterResult(False, False, None, f"connection_error: {exc}")
    envelope = _parse_envelope(resp)
    if envelope is None:
        return AdapterResult(False, False, None, "malformed JSON response")
    if resp.status_code == 201 and envelope.get("ok"):
        return AdapterResult(True, True, envelope.get("data"), "captured")
    error_code = (envelope.get("error") or {}).get("code")
    # 409 ORDER_NOT_APPROVED: buyer has not actually approved yet (or a race) -- not a
    # capture failure, never a double-capture risk; caller maps this to its own
    # NOT_APPROVED without changing order state.
    if resp.status_code == 409:
        return AdapterResult(False, False, None, "not_approved", code=error_code)
    # 403 AUTHORIZATION_MISMATCH / 422 UPSTREAM_REJECTED: definite, PayPal/adapter said no.
    if resp.status_code in (403, 422):
        return AdapterResult(
            False,
            True,
            None,
            f"definite failure status={resp.status_code}",
            code=error_code,
        )
    # 202 IN_PROGRESS (concurrent same request_id), 503/504 UNKNOWN/AUTH -- indefinite,
    # never retried blindly; caller reconciles via get_order before any second attempt.
    return AdapterResult(
        False, False, None, f"status={resp.status_code}", code=error_code
    )
