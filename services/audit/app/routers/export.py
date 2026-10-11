"""GET /export (NDJSON) -- api.md sec 5, spec.md sec 13. Reviewer/operator only.

One full row per line (seq, canonical, prev_hash, row_hash, ...), consumed by
`scripts/verify_chain_standalone.py`. No secrets by construction (redaction rules are
enforced at ingestion, spec.md sec 6).

Role check: spec.md sec 17 flags that no stable reviewer/operator role string exists yet
(same open item as entries.py); this wave treats any verified non-buyer principal as
export-eligible and flags the gap rather than inventing a role string.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import ProducerClaims, verify_internal_token
from app.settings import Settings, get_settings

router = APIRouter(tags=["export"])

_EXPORT_COLUMNS = (
    "seq, chain_id, event_id, event_type, event_version, producer, occurred_at,"
    " recorded_at, actor_type, actor_id, auth_method, request_id, trace_id, buyer_id,"
    " mandate_id, order_id, case_id, canonical, prev_hash, row_hash"
)


@router.get("/export")
async def export_chain(
    from_seq: int | None = None,
    to_seq: int | None = None,
    claims: ProducerClaims = Depends(verify_internal_token),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    act = claims.act or {}
    if act.get("type") == "buyer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "role_not_allowed", "detail": "export is reviewer/operator only"},
        )

    start_seq = from_seq or 1
    max_rows = settings.page_max * 10

    conditions = ["seq >= :start_seq"]
    params: dict = {"start_seq": start_seq, "limit": max_rows}
    if to_seq is not None:
        conditions.append("seq <= :end_seq")
        params["end_seq"] = to_seq

    export_query = text(
        f"SELECT {_EXPORT_COLUMNS} FROM entries WHERE {' AND '.join(conditions)}"
        " ORDER BY seq ASC LIMIT :limit"
    )
    rows = (await session.execute(export_query, params)).mappings().all()

    async def _stream() -> AsyncIterator[bytes]:
        for row in rows:
            d = dict(row)
            d["event_id"] = str(d["event_id"])
            d["occurred_at"] = d["occurred_at"].isoformat()
            d["recorded_at"] = d["recorded_at"].isoformat()
            yield (json.dumps(d) + "\n").encode("utf-8")

    return StreamingResponse(_stream(), media_type="application/x-ndjson")
