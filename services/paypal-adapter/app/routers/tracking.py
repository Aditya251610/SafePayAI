"""add_tracking / get_tracking -- api.md section 4/5.5-5.6. Caller: tracking only.

Wave 4: validated stubs, caller allowlist enforced, 501.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.deps import Caller, require_tool_permission
from app.schemas.envelope import not_implemented_envelope
from app.schemas.orders import AddTrackingRequest

router = APIRouter(prefix="/v1", tags=["tracking"])


@router.post("/orders/{order_id}/track", status_code=501)
async def add_tracking(
    order_id: str,
    body: AddTrackingRequest,
    _caller: Caller = Depends(require_tool_permission("add_tracking")),  # noqa: B008
) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=not_implemented_envelope("add_tracking pending Wave 5", str(uuid.uuid4())),
    )


@router.get("/orders/{order_id}/trackers/{tracker_id}", status_code=501)
async def get_tracking(
    order_id: str,
    tracker_id: str,
    _caller: Caller = Depends(require_tool_permission("get_tracking")),  # noqa: B008
) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=not_implemented_envelope("get_tracking pending Wave 5", str(uuid.uuid4())),
    )
