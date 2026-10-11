"""Generic proxy handler (spec.md section 2 `routing/proxy.py`, section 5.2 / 8).

Drives every `/api/<svc>/*` route: mints one internal JWT per upstream call, builds
the outbound request from an explicit header allowlist (so `Cookie`, inbound
`Authorization`, and the `X-User-*`/`X-Actor-*`/`X-Role*`/`X-Auth-*`/`X-Internal-*`/
`X-Forwarded-*` families are never forwarded - they are simply never read into the
allowlisted dict in the first place), forwards to the owning service, and passes
the response back with only the allowlisted response headers.

Scope cuts for this pass (flagged in the final report, not in this task's six
numbered IMPLEMENT items): no retry-on-idempotent-GET/keyed-POST loop, no
forbidden-money-key body scan, no `approval_url` host allowlist, no response
caching headers logic beyond pass-through. `PS_APIGATEWAY_MONEY_ROUTES_ENABLED`
and `Idempotency-Key` enforcement ARE implemented here since they are cheap,
request-shape-only checks the task's proxy-correctness goal depends on.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from fastapi import Request, Response

from app.deps import Principal
from app.settings import get_settings
from app.tokens.mint import mint_for_upstream
from app.upstream import UpstreamNotConfigured, get_upstream_client

ALLOWED_REQUEST_HEADERS = {
    "content-type",
    "accept",
    "idempotency-key",
    "if-match",
    "if-none-match",
}
ALLOWED_RESPONSE_HEADERS = {"content-type", "cache-control", "retry-after", "etag"}


def _request_id(request: Request) -> str:
    # Inbound X-Request-Id is intentionally ignored (spec.md section 8); gateway
    # always mints its own and echoes it.
    return str(uuid.uuid4())


async def forward(
    request: Request,
    response: Response,
    *,
    service: str,
    upstream_path: str,
    method: str,
    principal: Principal | None,
    scope: list[str] | None = None,
    body: Any = None,
    require_idempotency: bool = False,
    money_route: bool = False,
    mandate_id: str | None = None,
) -> Any:
    settings = get_settings()
    request_id = _request_id(request)
    response.headers["X-Request-Id"] = request_id

    if money_route and not settings.money_routes_enabled:
        response.status_code = 503
        return {
            "error": "MONEY_ROUTES_DISABLED",
            "message": "Money-moving routes are disabled.",
            "request_id": request_id,
        }

    if require_idempotency and not request.headers.get("Idempotency-Key"):
        response.status_code = 400
        return {
            "error": "IDEMPOTENCY_KEY_REQUIRED",
            "message": "Idempotency-Key header is required for this request.",
            "request_id": request_id,
        }

    headers = {
        k: v for k, v in request.headers.items() if k.lower() in ALLOWED_REQUEST_HEADERS
    }

    try:
        token = mint_for_upstream(
            principal,
            audience=service,
            request_id=request_id,
            scope=scope or [],
            mandate_id=mandate_id,
        )
    except RuntimeError:
        response.status_code = 503
        return {
            "error": "UPSTREAM_UNAVAILABLE",
            "message": "Signing key is not available.",
            "request_id": request_id,
        }

    headers["Authorization"] = f"Bearer {token}"
    headers["X-Request-Id"] = request_id

    try:
        client = get_upstream_client(service, settings)
    except UpstreamNotConfigured:
        response.status_code = 503
        return {
            "error": "UPSTREAM_UNAVAILABLE",
            "message": f"{service} is not configured.",
            "request_id": request_id,
        }

    try:
        upstream_response = await client.request(
            method,
            upstream_path,
            params=dict(request.query_params),
            headers=headers,
            json=body,
        )
    except httpx.ConnectTimeout:
        response.status_code = 503
        response.headers["Retry-After"] = "3"
        return {
            "error": "UPSTREAM_WAKING",
            "message": "Upstream is waking up, retry shortly.",
            "request_id": request_id,
        }
    except httpx.ConnectError:
        response.status_code = 503
        return {
            "error": "UPSTREAM_UNAVAILABLE",
            "message": f"{service} is unreachable.",
            "request_id": request_id,
        }
    except httpx.ReadTimeout:
        response.status_code = 504
        return {
            "error": "UPSTREAM_TIMEOUT",
            "message": f"{service} timed out.",
            "request_id": request_id,
        }

    response.status_code = upstream_response.status_code
    for h, v in upstream_response.headers.items():
        if h.lower() in ALLOWED_RESPONSE_HEADERS:
            response.headers[h] = v

    if not upstream_response.content:
        return None
    try:
        return upstream_response.json()
    except ValueError:
        response.status_code = 502
        return {
            "error": "UPSTREAM_BAD_RESPONSE",
            "message": "Upstream returned a non-JSON body.",
            "request_id": request_id,
        }
