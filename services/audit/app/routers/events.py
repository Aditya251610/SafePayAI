"""POST /internal/events, POST /internal/events/batch -- api.md sec 1.

Wave 4: envelope-shape validation (pydantic) and caller JWT verification are real;
the append algorithm itself (canonicalization, advisory-lock linkage, actor/producer
allowlist, idempotency on event_id -- spec.md sec 3/5) is Wave 5 business logic.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.deps import ProducerClaims, verify_internal_token
from app.schemas.events import EventBatchRequest, EventEnvelope

router = APIRouter(prefix="/internal/events", tags=["ingestion"])


def _not_implemented(endpoint: str) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={"error": "not_implemented", "detail": f"{endpoint} pending Wave 5", "request_id": None},
    )


@router.post("")
async def append_event(
    envelope: EventEnvelope,
    claims: ProducerClaims = Depends(verify_internal_token),
) -> JSONResponse:
    return _not_implemented("POST /internal/events")


@router.post("/batch")
async def append_events_batch(
    body: EventBatchRequest,
    claims: ProducerClaims = Depends(verify_internal_token),
) -> JSONResponse:
    return _not_implemented("POST /internal/events/batch")
