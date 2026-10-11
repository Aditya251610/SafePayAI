"""POST /v1/reconcile/{request_id} -- api.md section 4. Wave 4: validated stub, 501."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.deps import Caller, require_internal_jwt
from app.schemas.envelope import not_implemented_envelope

router = APIRouter(prefix="/v1", tags=["reconcile"])


@router.post("/reconcile/{request_id}", status_code=501)
async def reconcile(
    request_id: str,
    _caller: Caller = Depends(require_internal_jwt),
) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=not_implemented_envelope("reconcile pending Wave 5", str(uuid.uuid4())),
    )
