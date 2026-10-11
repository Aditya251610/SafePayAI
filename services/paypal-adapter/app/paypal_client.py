"""httpx wrapper for PayPal sandbox REST: OAuth2 client-credentials token cache (memory
only, single-flight), 401-retry-once, and the three S1-08 calls (create_order, get_order,
capture_order). Per spec.md section 1: imports nothing from `ops`; knows nothing of
tickets or callers. Per spec.md section 9: token refreshed proactively near expiry AND on
a 401 (invalidate, refresh once, retry the identical request once, then
`UPSTREAM_AUTH_FAILED`). Credentials come only from the bare PAYPAL_CLIENT_ID/SECRET env
vars (settings.py); never logged, never put in exception messages.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.settings import Settings


class PayPalAuthError(Exception):
    """Raised after the single 401-retry still fails. Maps to UPSTREAM_AUTH_FAILED."""


class PayPalUpstreamError(Exception):
    """Non-auth transport/5xx failure. `status_code` None means no response was received
    (timeout/connection error) -- callers map this to ledger state UNKNOWN."""

    def __init__(self, message: str, status_code: int | None, paypal_name: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.paypal_name = paypal_name


@dataclass
class _CachedToken:
    access_token: str
    expires_at: float


class PayPalClient:
    """One instance per process; the token cache and the asyncio lock are per-instance
    state, which is what makes single-flight refresh work (spec.md section 9)."""

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self._settings = settings
        self._token: _CachedToken | None = None
        self._lock: Any = None  # created lazily; asyncio.Lock() needs a running loop
        self._client = httpx.AsyncClient(
            base_url=settings.paypal_base_url,
            timeout=settings.paypal_timeout_seconds,
            transport=transport,
            follow_redirects=False,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _get_lock(self) -> Any:
        import asyncio

        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _token_fresh(self) -> bool:
        if self._token is None:
            return False
        skew = self._settings.paypal_token_refresh_skew_seconds
        return time.time() < (self._token.expires_at - skew)

    async def _fetch_token(self) -> _CachedToken:
        client_id = self._settings.paypal_client_id
        client_secret = self._settings.paypal_client_secret
        if not client_id or not client_secret:
            raise PayPalAuthError("PayPal credentials not configured")
        resp = await self._client.post(
            "/v1/oauth2/token",
            data={"grant_type": "client_credentials"},
            auth=(client_id, client_secret),
            headers={"Accept": "application/json"},
        )
        if resp.status_code != 200:
            raise PayPalAuthError(f"token request failed with status {resp.status_code}")
        body = resp.json()
        now = time.time()
        return _CachedToken(
            access_token=body["access_token"],
            expires_at=now + float(body.get("expires_in", 32000)),
        )

    async def _get_token(self, force_refresh: bool = False) -> str:
        if not force_refresh and self._token_fresh():
            return self._token.access_token  # type: ignore[union-attr]
        async with self._get_lock():
            # Re-check inside the lock: another coroutine may have just refreshed.
            if not force_refresh and self._token_fresh():
                return self._token.access_token  # type: ignore[union-attr]
            self._token = await self._fetch_token()
            return self._token.access_token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> httpx.Response:
        """Issues one call with the cached token; on 401, invalidates, refreshes once,
        and retries the identical request once (same request_id -> same PayPal-Request-Id
        header), then raises PayPalAuthError (spec.md section 9, PA-C02)."""
        for attempt in (1, 2):
            token = await self._get_token(force_refresh=(attempt == 2))
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            if request_id is not None:
                headers["PayPal-Request-Id"] = request_id
            try:
                resp = await self._client.request(method, path, json=json_body, headers=headers)
            except httpx.TimeoutException as exc:
                raise PayPalUpstreamError("upstream timeout", status_code=None) from exc
            except httpx.TransportError as exc:
                raise PayPalUpstreamError("upstream connection error", status_code=None) from exc
            if resp.status_code == 401:
                self._token = None
                if attempt == 2:
                    raise PayPalAuthError("PayPal rejected the refreshed token")
                continue
            return resp
        raise PayPalAuthError("PayPal rejected the refreshed token")

    @staticmethod
    def _error_name(resp: httpx.Response) -> str | None:
        try:
            body = resp.json()
        except ValueError:
            return None
        name = body.get("name") if isinstance(body, dict) else None
        return str(name) if name else None

    # -- the three S1-08 operations -------------------------------------------------

    async def create_order(
        self,
        *,
        request_id: str,
        amount_minor: int,
        currency: str,
        custom_id: str,
        invoice_id: str,
        return_url: str,
        cancel_url: str,
    ) -> dict[str, Any]:
        value = f"{amount_minor // 100}.{amount_minor % 100:02d}"
        body = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "custom_id": custom_id,
                    "invoice_id": invoice_id,
                    "amount": {"currency_code": currency, "value": value},
                }
            ],
            "application_context": {
                "return_url": return_url,
                "cancel_url": cancel_url,
            },
        }
        resp = await self._request(
            "POST", "/v2/checkout/orders", json_body=body, request_id=request_id
        )
        if resp.status_code not in (200, 201):
            raise PayPalUpstreamError(
                "create_order failed",
                status_code=resp.status_code,
                paypal_name=self._error_name(resp),
            )
        return dict(resp.json())

    async def get_order(self, order_id: str) -> dict[str, Any]:
        resp = await self._request("GET", f"/v2/checkout/orders/{order_id}")
        if resp.status_code != 200:
            raise PayPalUpstreamError(
                "get_order failed", status_code=resp.status_code, paypal_name=self._error_name(resp)
            )
        return dict(resp.json())

    async def capture_order(self, order_id: str, *, request_id: str) -> dict[str, Any]:
        resp = await self._request(
            "POST", f"/v2/checkout/orders/{order_id}/capture", json_body={}, request_id=request_id
        )
        if resp.status_code not in (200, 201):
            raise PayPalUpstreamError(
                "capture_order failed",
                status_code=resp.status_code,
                paypal_name=self._error_name(resp),
            )
        return dict(resp.json())


_client_singleton: PayPalClient | None = None


def _build_singleton(settings: Settings) -> PayPalClient:
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = PayPalClient(settings)
    return _client_singleton


def get_paypal_client_for(settings: Settings) -> PayPalClient:
    """Plain helper -- callers (tests, scripts) pass `settings` explicitly."""
    return _build_singleton(settings)


def get_paypal_client() -> PayPalClient:
    """FastAPI dependency with no request-derived params. Deliberately does NOT take a
    `settings: Settings` parameter without wrapping it in `Depends(get_settings)`: FastAPI
    introspects sub-dependency callables and treats a bare Pydantic-model parameter as an
    implicit request-body field, which silently turns every route using this dependency
    into "expects a nested {'body': ...} JSON shape" (discovered via a 422 on every S1-08
    integration test; see app.settings.get_settings for the correctly-wrapped pattern)."""
    from app.settings import get_settings

    return _build_singleton(get_settings())
