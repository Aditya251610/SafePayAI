"""GET /head -- api.md sec 4, spec.md sec 10."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.deps import ProducerClaims, verify_internal_token

router = APIRouter(tags=["head"])


@router.get("/head")
async def get_head(claims: ProducerClaims = Depends(verify_internal_token)) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={"error": "not_implemented", "detail": "GET /head pending Wave 5", "request_id": None},
    )
