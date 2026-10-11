"""GET /v1/refunds/{id} -- api.md section 4/5.8. Wave 4: validated stub, 501."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.deps import Caller, require_tool_permission
from app.schemas.envelope import not_implemented_envelope

router = APIRouter(prefix="/v1", tags=["refunds"])


@router.get("/refunds/{refund_id}", status_code=501)
async def get_refund(
    refund_id: str,
    _caller: Caller = Depends(require_tool_permission("get_refund")),
) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=not_implemented_envelope("get_refund pending Wave 5", str(uuid.uuid4())),
    )
