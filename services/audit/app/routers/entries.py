"""GET /entries, GET /entries/{seq}, GET /entries/by-ref -- api.md sec 2.

Route order matters: /by-ref is registered before the /{seq} int-typed path so it is
never swallowed by the int converter.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.deps import ProducerClaims, verify_internal_token

router = APIRouter(prefix="/entries", tags=["read"])


def _not_implemented(endpoint: str) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={"error": "not_implemented", "detail": f"{endpoint} pending Wave 5", "request_id": None},
    )


@router.get("")
async def list_entries(
    startRow: int | None = Query(default=None),
    endRow: int | None = Query(default=None),
    sort: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    family: str | None = Query(default=None),
    actor_type: str | None = Query(default=None),
    actor_id: str | None = Query(default=None),
    mandate_id: str | None = Query(default=None),
    order_id: str | None = Query(default=None),
    case_id: str | None = Query(default=None),
    request_id: str | None = Query(default=None),
    trace_id: str | None = Query(default=None),
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    after_seq: int | None = Query(default=None),
    before_seq: int | None = Query(default=None),
    claims: ProducerClaims = Depends(verify_internal_token),
) -> JSONResponse:
    return _not_implemented("GET /entries")


@router.get("/by-ref")
async def entries_by_ref(
    mandate_id: str | None = Query(default=None),
    order_id: str | None = Query(default=None),
    case_id: str | None = Query(default=None),
    claims: ProducerClaims = Depends(verify_internal_token),
) -> JSONResponse:
    return _not_implemented("GET /entries/by-ref")


@router.get("/{seq}")
async def get_entry(seq: int, claims: ProducerClaims = Depends(verify_internal_token)) -> JSONResponse:
    return _not_implemented("GET /entries/{seq}")
