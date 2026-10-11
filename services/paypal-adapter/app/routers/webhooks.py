"""POST /v1/webhooks/paypal -- optional, PS_PAYPALADAPTER_WEBHOOK_ENABLED=false default
(api.md section 4; deployment.md section 5). Hint only, never authoritative. Wave 4 stub.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.schemas.envelope import not_implemented_envelope
from app.settings import get_settings

router = APIRouter(prefix="/v1", tags=["webhooks"])


@router.post("/webhooks/paypal", status_code=501)
async def paypal_webhook(request: Request) -> JSONResponse:
    settings = get_settings()
    if not settings.webhook_enabled:
        return JSONResponse(status_code=404, content={"error": "not_found", "detail": "disabled", "request_id": None})
    return JSONResponse(
        status_code=501,
        content=not_implemented_envelope("webhook handling pending Wave 5", str(uuid.uuid4())),
    )
