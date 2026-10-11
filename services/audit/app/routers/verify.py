"""GET /verify, GET /verify/last -- api.md sec 3, spec.md sec 7."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.deps import ProducerClaims, verify_internal_token

router = APIRouter(tags=["verify"])


def _not_implemented(endpoint: str) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={"error": "not_implemented", "detail": f"{endpoint} pending Wave 5", "request_id": None},
    )


@router.get("/verify")
async def verify_chain(
    anchor_seq: int | None = Query(default=None),
    anchor_hash: str | None = Query(default=None),
    from_seq: int | None = Query(default=None),
    from_hash: str | None = Query(default=None),
    claims: ProducerClaims = Depends(verify_internal_token),
) -> JSONResponse:
    return _not_implemented("GET /verify")


@router.get("/verify/last")
async def verify_last(claims: ProducerClaims = Depends(verify_internal_token)) -> JSONResponse:
    return _not_implemented("GET /verify/last")
