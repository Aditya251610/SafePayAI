"""GET /v1/control/status, POST /v1/control/freeze|unfreeze -- api.md section 4.

Wave 4: validated stubs, 501. Real control_flags DB read/write is Wave 5.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.deps import Caller, require_internal_jwt
from app.schemas.envelope import not_implemented_envelope

router = APIRouter(prefix="/v1/control", tags=["control"])


@router.get("/status", status_code=501)
async def control_status(_caller: Caller = Depends(require_internal_jwt)) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=not_implemented_envelope("control status pending Wave 5", str(uuid.uuid4())),
    )


@router.post("/freeze", status_code=501)
async def control_freeze(_caller: Caller = Depends(require_internal_jwt)) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=not_implemented_envelope("control freeze pending Wave 5", str(uuid.uuid4())),
    )


@router.post("/unfreeze", status_code=501)
async def control_unfreeze(_caller: Caller = Depends(require_internal_jwt)) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=not_implemented_envelope("control unfreeze pending Wave 5", str(uuid.uuid4())),
    )
