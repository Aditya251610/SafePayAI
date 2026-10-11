"""POST /propose, GET /propose/{proposal_id} -- api.md sections 4, 6.

Wave 4: request validated against the contract schema, then 501. No LLM call, no catalog/
mandate call, no DB write. Business logic is Wave 5.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.deps import ServicePrincipal, require_service_jwt
from app.schemas.propose import ProposeRequest

router = APIRouter(tags=["propose"])


@router.post("/propose", status_code=501)
async def propose(
    body: ProposeRequest,
    _principal: ServicePrincipal = Depends(require_service_jwt),
) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={
            "error": "not_implemented",
            "detail": "POST /propose pending Wave 5",
            "request_id": None,
        },
    )


@router.get("/propose/{proposal_id}", status_code=501)
async def get_propose(
    proposal_id: str,
    _principal: ServicePrincipal = Depends(require_service_jwt),
) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={
            "error": "not_implemented",
            "detail": "GET /propose/{proposal_id} pending Wave 5",
            "request_id": None,
        },
    )
