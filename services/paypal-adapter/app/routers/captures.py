"""GET /v1/captures/{id}, POST /v1/captures/{id}/refund -- api.md section 4/5.4/5.7.

Wave 4: validated stubs, caller allowlist enforced, 501. refund_capture (not create_refund,
per the confirmed rename) is the money tool name.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.deps import Caller, require_authorization_ticket, require_tool_permission
from app.schemas.envelope import not_implemented_envelope
from app.schemas.orders import RefundCaptureRequest

router = APIRouter(prefix="/v1", tags=["captures"])


@router.get("/captures/{capture_id}", status_code=501)
async def get_capture(
    capture_id: str,
    _caller: Caller = Depends(require_tool_permission("get_capture")),
) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=not_implemented_envelope("get_capture pending Wave 5", str(uuid.uuid4())),
    )


@router.post("/captures/{capture_id}/refund", status_code=501)
async def refund_capture(
    capture_id: str,
    body: RefundCaptureRequest,
    _caller: Caller = Depends(require_tool_permission("refund_capture")),
    _ticket: str = Depends(require_authorization_ticket),
) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=not_implemented_envelope("refund_capture pending Wave 5", str(uuid.uuid4())),
    )
