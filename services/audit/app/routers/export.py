"""GET /export (NDJSON) -- api.md sec 5, spec.md sec 13. Reviewer/operator only."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.deps import ProducerClaims, verify_internal_token

router = APIRouter(tags=["export"])


@router.get("/export")
async def export_chain(
    from_seq: int | None = Query(default=None),
    to_seq: int | None = Query(default=None),
    claims: ProducerClaims = Depends(verify_internal_token),
) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={"error": "not_implemented", "detail": "GET /export pending Wave 5", "request_id": None},
    )
