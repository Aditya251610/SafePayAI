"""POST /intent-fit -- api.md section 5. Service-to-service only (svc:checkout).

Wave 4: validated stub, 501. Advisory-only logic (never clears a hard block) is Wave 5.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.deps import ServicePrincipal, require_checkout_caller
from app.schemas.propose import IntentFitRequest

router = APIRouter(tags=["intent-fit"])


@router.post("/intent-fit", status_code=501)
async def intent_fit(
    body: IntentFitRequest,
    _principal: ServicePrincipal = Depends(require_checkout_caller),
) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={
            "error": "not_implemented",
            "detail": "POST /intent-fit pending Wave 5",
            "request_id": None,
        },
    )
