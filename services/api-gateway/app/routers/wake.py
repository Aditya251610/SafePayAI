"""GET /api/wake: start waking sleeping backend hosts (free-tier cold starts).

Public and harmless: it only issues GETs to the health URLs listed in
PS_APIGATEWAY_WAKE_URLS (operator-configured, never from the request) and returns how many
it pinged. The frontend calls it fire-and-forget so a sleeping host is already waking
before a buyer reaches a money step (live: a sleeping PayPal host failed order creation).
"""

from __future__ import annotations

import asyncio

import httpx
from fastapi import APIRouter, Depends, Request, Response

from app.ratelimit import limiter
from app.routers.auth import _client_ip
from app.settings import Settings, get_settings

router = APIRouter(prefix="/api", tags=["wake"])

WAKE_RATE_LIMIT = 12
WAKE_WINDOW_S = 60.0
WAKE_TIMEOUT_S = 2.5


async def _ping(client: httpx.AsyncClient, url: str) -> None:
    try:
        await client.get(url)
    except httpx.HTTPError:
        pass  # a timeout still wakes the host; nothing to report


@router.get("/wake")
async def wake(
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> dict:
    allowed, retry_after = limiter.check(
        f"wake:{_client_ip(request, settings)}", WAKE_RATE_LIMIT, WAKE_WINDOW_S
    )
    if not allowed:
        response.status_code = 429
        response.headers["Retry-After"] = str(int(retry_after) + 1)
        return {
            "error": "RATE_LIMITED",
            "message": "Too many requests, try again later.",
        }
    urls = [u.strip() for u in (settings.wake_urls or "").split(",") if u.strip()]
    if urls:
        async with httpx.AsyncClient(timeout=WAKE_TIMEOUT_S) as client:
            await asyncio.gather(*(_ping(client, u) for u in urls))
    return {"pinged": len(urls)}
