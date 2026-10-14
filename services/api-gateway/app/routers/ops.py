"""Ops surface: freeze flag read/write, demo mode + build info, cron tick
(spec.md section 5.1 / 10, api.md's ops section, REQ-GW-041/044).

GET /status and POST /freeze forward to resolution's own refunds_frozen flag
(resolution/api.md section 3.11) via the normal proxy path -- resolution owns the
flag and audits the change itself (spec.md C6); the gateway never evaluates it for
refund enforcement (threat-model section 10). resolution's real enforcement is
operator-only, stricter than this doc's original "B,M,O can read status" aspiration
-- a non-operator's status read degrades to "unknown" (treated as frozen by the UI,
same fail-closed posture as an unreachable owner) rather than leaking a 403.

POST /tick mints a `sub=svc:poller` system token (not used here -- see below) and
drives tracking's + resolution's own `/internal/tick` directly over their shared
X-Tick-Secret header, same mechanism `.github/workflows/outbox-flush.yml` already
uses service-to-service; this route is the on-demand equivalent (e.g. a "run tick
now" demo control) rather than a replacement for that cron job. A system JWT
wouldn't work for resolution's /internal/tick -- it's gated by X-Tick-Secret only,
not an internal JWT at all.
"""

from __future__ import annotations

import hmac
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Header, Request, Response

from app.csrf import require_csrf
from app.deps import Principal, require_operator, require_session
from app.routing.proxy import forward
from app.schemas.ops import FreezeRequest
from app.settings import get_settings
from app.upstream import UpstreamNotConfigured, get_upstream_client

router = APIRouter(prefix="/api/ops", tags=["ops"])


@router.get("/status")
async def status(
    request: Request,
    response: Response,
    principal: Principal = Depends(require_session),
) -> dict:
    settings = get_settings()
    upstream = await forward(
        request,
        response,
        service="resolution",
        upstream_path="/controls/refunds-frozen",
        method="GET",
        principal=principal,
        scope=["resolution:controls"],
    )
    if response.status_code == 200 and isinstance(upstream, dict):
        refunds_frozen = str(upstream.get("refunds_frozen", "unknown")).lower()
    else:
        # Owner unreachable, or caller isn't an operator (resolution's real role
        # check) -- either way this status read must degrade to "unknown", not
        # leak the upstream error code (spec.md: "unknown ... shown as frozen").
        refunds_frozen = "unknown"
    response.status_code = 200
    return {
        "demo_mode": settings.demo_mode,
        "money_routes_enabled": settings.money_routes_enabled,
        "refunds_frozen": refunds_frozen,
        "build_id": settings.build_id,
    }


@router.post("/freeze")
async def freeze(
    request: Request,
    body: FreezeRequest,
    response: Response,
    principal: Principal = Depends(require_operator),
    _csrf: None = Depends(require_csrf("ops_freeze")),
) -> Any:
    upstream = await forward(
        request,
        response,
        service="resolution",
        upstream_path="/controls/refunds-frozen",
        method="PUT",
        principal=principal,
        scope=["resolution:controls"],
        body={"refunds_frozen": body.frozen, "reason": body.reason or ""},
        money_route=True,
    )
    return upstream


@router.post("/tick")
async def tick(
    request: Request,
    response: Response,
    x_tick_secret: str | None = Header(default=None, alias="X-Tick-Secret"),
) -> dict:
    settings = get_settings()
    if not x_tick_secret or not settings.tick_secret:
        response.status_code = 401
        return {
            "error": "UNAUTHENTICATED",
            "message": "missing or unconfigured tick secret",
        }
    if not hmac.compare_digest(x_tick_secret, settings.tick_secret):
        response.status_code = 401
        return {"error": "UNAUTHENTICATED", "message": "invalid tick secret"}

    async def _drive(service: str, path: str, secret: str | None) -> str:
        if not secret:
            return "unconfigured"
        try:
            client = get_upstream_client(service, settings)
        except UpstreamNotConfigured:
            return "unavailable"
        try:
            resp = await client.post(path, headers={"X-Tick-Secret": secret})
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout):
            return "unavailable"
        return "accepted" if resp.status_code < 300 else "failed"

    detector = await _drive("tracking", "/internal/tick", settings.tracking_tick_secret)
    reconcile = await _drive(
        "resolution", "/internal/tick", settings.resolution_tick_secret
    )
    response.status_code = 202
    return {"detector": detector, "reconcile": reconcile}
