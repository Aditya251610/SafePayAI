"""GET /verify, GET /verify/last -- api.md sec 3, spec.md sec 7.

Always HTTP 200 for /verify; `ok` carries the verdict. Every call inserts one
`verify_runs` row (informational, spec.md sec 2.2).
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app_audit.chain.verify import verify_chain
from app_audit.db import get_session
from app_audit.deps import ProducerClaims, verify_internal_token
from app_audit.settings import Settings, get_settings

router = APIRouter(tags=["verify"])


@router.get("/verify")
async def verify_chain_endpoint(
    anchor_seq: int | None = Query(default=None),
    anchor_hash: str | None = Query(default=None),
    from_seq: int | None = Query(default=None),
    from_hash: str | None = Query(default=None),
    claims: ProducerClaims = Depends(verify_internal_token),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    head_before = (
        await session.execute(text("SELECT COALESCE(MAX(seq), 0) FROM entries"))
    ).scalar_one()

    result = await verify_chain(
        session,
        chunk_size=settings.verify_chunk,
        expected_chain_id=settings.chain_id,
        anchor_seq=anchor_seq,
        anchor_hash=anchor_hash,
    )

    act = claims.act or {}
    await session.execute(
        text(
            "INSERT INTO verify_runs (started_at, finished_at, head_seq_at_start, ok,"
            " first_bad_seq, reason, requested_by_actor_id, request_id)"
            " VALUES (:started_at, :finished_at, :head_seq_at_start, :ok, :first_bad_seq,"
            " :reason, :actor_id, :request_id)"
        ),
        {
            "started_at": datetime.now(UTC),
            "finished_at": datetime.now(UTC),
            "head_seq_at_start": head_before,
            "ok": result.ok,
            "first_bad_seq": result.first_bad_seq,
            "reason": result.reason,
            "actor_id": act.get("id"),
            "request_id": claims.request_id,
        },
    )
    await session.commit()

    body: dict = {
        "ok": result.ok,
        "chain_id": result.chain_id,
        "checked": result.checked,
        "head_seq": result.head_seq,
        "head_hash": result.head_hash,
        "algorithm": result.algorithm,
        "duration_ms": result.duration_ms,
        "anchor": result.anchor,
    }
    if not result.ok:
        body["first_bad_seq"] = result.first_bad_seq
        body["reason"] = result.reason
        body["expected"] = result.expected
        body["found"] = result.found
    elif result.reason:
        # Honest-limit case (spec.md sec 11/12 step C): chain internally consistent
        # (ok=True) but the anchor check still failed -- surfaced via anchor.ok + reason.
        body["reason"] = result.reason

    return JSONResponse(status_code=200, content=jsonable_encoder(body))


@router.get("/verify/last")
async def verify_last(
    claims: ProducerClaims = Depends(verify_internal_token),
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    row = (
        await session.execute(
            text(
                "SELECT id, started_at, finished_at, head_seq_at_start, ok, first_bad_seq, reason"
                " FROM verify_runs ORDER BY id DESC LIMIT 1"
            )
        )
    ).first()
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"error": "not_found", "detail": "no verify runs yet", "request_id": None},
        )
    return JSONResponse(status_code=200, content=jsonable_encoder(dict(row._mapping)))
