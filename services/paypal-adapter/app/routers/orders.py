"""POST /v1/orders, GET /v1/orders/{id}, POST /v1/orders/{id}/capture -- api.md section 4/5.1-5.3.

Wave 4: request validated, caller allowlist enforced (NOT_PERMITTED on denial), then 501.
No real PayPal call -- that is Wave 5. Ticket verification wiring (auth.ticket.verify_ticket)
lands with the real implementation in Wave 5; Wave 4 only requires the header be present.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.deps import Caller, require_authorization_ticket, require_tool_permission
from app.schemas.envelope import not_implemented_envelope
from app.schemas.orders import CaptureOrderRequest, CreateOrderRequest

router = APIRouter(prefix="/v1", tags=["orders"])


@router.post("/orders", status_code=501)
async def create_order(
    body: CreateOrderRequest,
    _caller: Caller = Depends(require_tool_permission("create_order")),
    _ticket: str = Depends(require_authorization_ticket),
) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=not_implemented_envelope("create_order pending Wave 5", str(uuid.uuid4())),
    )


@router.get("/orders/{order_id}", status_code=501)
async def get_order(
    order_id: str,
    _caller: Caller = Depends(require_tool_permission("get_order")),
) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=not_implemented_envelope("get_order pending Wave 5", str(uuid.uuid4())),
    )


@router.post("/orders/{order_id}/capture", status_code=501)
async def capture_order(
    order_id: str,
    body: CaptureOrderRequest,
    _caller: Caller = Depends(require_tool_permission("capture_order")),
    _ticket: str = Depends(require_authorization_ticket),
) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=not_implemented_envelope("capture_order pending Wave 5", str(uuid.uuid4())),
    )
