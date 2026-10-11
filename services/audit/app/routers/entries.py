"""GET /entries, GET /entries/{seq}, GET /entries/by-ref -- api.md sec 2.

Route order matters: /by-ref is registered before the /{seq} int-typed path so it is
never swallowed by the int converter.

Role scoping (spec.md sec 9, api.md sec 2/7): the verified gateway-minted token carries
`act` (principal). A buyer principal is scoped to `buyer_id = act.id`; any other
principal (merchant/reviewer/operator/service) sees all rows in this wave -- full
per-family merchant scoping (api.md sec 2 "order-side families") is flagged below as a
simplification, since the merchant-event-family allowlist is not yet defined anywhere
in the read docs beyond the name "order-side families".
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import ProducerClaims, verify_internal_token
from app.settings import Settings, get_settings

router = APIRouter(prefix="/entries", tags=["read"])

_SORT_COLUMNS = {"seq", "recorded_at", "event_type", "actor_id"}

_LIST_COLUMNS = (
    "seq, recorded_at, event_type, actor_type, actor_id, auth_method, request_id,"
    " mandate_id, order_id, case_id, payload, row_hash, prev_hash"
)


def _summary(event_type: str) -> str:
    """Server-side, payload-free summary label (api.md sec 2: "no free text")."""
    return event_type.replace("_", " ").title()


def _payload_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return {}
    return value or {}


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "seq": row.seq,
        "recorded_at": row.recorded_at,
        "event_type": row.event_type,
        "actor_type": row.actor_type,
        "actor_id": row.actor_id,
        "auth_method": row.auth_method,
        "request_id": row.request_id,
        "mandate_id": row.mandate_id,
        "order_id": row.order_id,
        "case_id": row.case_id,
        "summary": _summary(row.event_type),
        "row_hash_short": row.row_hash[:8],
        "prev_hash_short": row.prev_hash[:8],
    }


def _buyer_scope(claims: ProducerClaims) -> str | None:
    act = claims.act or {}
    if act.get("type") == "buyer":
        return act.get("id")
    return None


@router.get("")
async def list_entries(
    startRow: int = Query(default=0),
    endRow: int = Query(default=50),
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
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    page_size = min(max(endRow - startRow, 1), settings.page_max)

    conditions: list[str] = []
    params: dict[str, Any] = {}

    buyer_scope = _buyer_scope(claims)
    if buyer_scope is not None:
        # Buyer asking for another buyer's subject gets an empty set, not an error
        # (api.md sec 2, avoids ID probing): the scope condition always wins.
        conditions.append("buyer_id = :buyer_scope")
        params["buyer_scope"] = buyer_scope

    if event_type:
        conditions.append("event_type = ANY(:event_types)")
        params["event_types"] = [t.strip() for t in event_type.split(",") if t.strip()]
    if actor_type:
        conditions.append("actor_type = :actor_type")
        params["actor_type"] = actor_type
    if actor_id:
        conditions.append("actor_id = :actor_id")
        params["actor_id"] = actor_id
    if mandate_id:
        conditions.append("mandate_id = :mandate_id")
        params["mandate_id"] = mandate_id
    if order_id:
        conditions.append("order_id = :order_id")
        params["order_id"] = order_id
    if case_id:
        conditions.append("case_id = :case_id")
        params["case_id"] = case_id
    if request_id:
        conditions.append("request_id = :request_id")
        params["request_id"] = request_id
    if trace_id:
        conditions.append("trace_id = :trace_id")
        params["trace_id"] = trace_id
    if from_:
        conditions.append("recorded_at >= :from_ts")
        params["from_ts"] = from_
    if to:
        conditions.append("recorded_at <= :to_ts")
        params["to_ts"] = to
    if after_seq is not None:
        conditions.append("seq > :after_seq")
        params["after_seq"] = after_seq
    if before_seq is not None:
        conditions.append("seq < :before_seq")
        params["before_seq"] = before_seq

    sort_col, sort_dir = "seq", "DESC"
    if sort:
        parts = sort.split(":")
        col = parts[0]
        if col not in _SORT_COLUMNS:
            raise HTTPException(
                status_code=400,
                detail={"error": "bad_filter", "detail": f"unsupported sort column {col}"},
            )
        sort_col = col
        if len(parts) > 1 and parts[1].lower() == "asc":
            sort_dir = "ASC"

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params["limit"] = page_size
    list_query = text(
        f"SELECT {_LIST_COLUMNS} FROM entries {where_clause}"
        f" ORDER BY {sort_col} {sort_dir} LIMIT :limit"
    )
    rows = (await session.execute(list_query, params)).all()

    head_seq = (
        await session.execute(text("SELECT COALESCE(MAX(seq), 0) FROM entries"))
    ).scalar_one()
    last_row = startRow + len(rows) if len(rows) < page_size else -1
    if not conditions and last_row == -1:
        last_row = head_seq

    body = {"rows": [_row_to_dict(r) for r in rows], "lastRow": last_row, "head_seq": head_seq}
    return JSONResponse(status_code=200, content=jsonable_encoder(body))


@router.get("/by-ref")
async def entries_by_ref(
    mandate_id: str | None = Query(default=None),
    order_id: str | None = Query(default=None),
    case_id: str | None = Query(default=None),
    claims: ProducerClaims = Depends(verify_internal_token),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    candidates = (("mandate_id", mandate_id), ("order_id", order_id), ("case_id", case_id))
    chosen = next(((col, val) for col, val in candidates if val), None)
    if chosen is None:
        raise HTTPException(
            status_code=422,
            detail={"error": "bad_filter", "detail": "one of mandate_id/order_id/case_id required"},
        )
    col, val = chosen

    conditions = [f"{col} = :val"]
    params: dict[str, Any] = {"val": val, "limit": settings.page_max}
    buyer_scope = _buyer_scope(claims)
    if buyer_scope is not None:
        conditions.append("buyer_id = :buyer_scope")
        params["buyer_scope"] = buyer_scope

    by_ref_query = text(
        f"SELECT {_LIST_COLUMNS} FROM entries WHERE {' AND '.join(conditions)}"
        " ORDER BY seq ASC LIMIT :limit"
    )
    rows = (await session.execute(by_ref_query, params)).all()
    body = {"rows": [_row_to_dict(r) for r in rows]}
    return JSONResponse(status_code=200, content=jsonable_encoder(body))


@router.get("/{seq}")
async def get_entry(
    seq: int,
    claims: ProducerClaims = Depends(verify_internal_token),
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    row = (
        await session.execute(
            text(
                "SELECT seq, recorded_at, event_type, actor_type, actor_id, auth_method,"
                " request_id, mandate_id, order_id, case_id, buyer_id, payload, prev_hash,"
                " row_hash, canonical FROM entries WHERE seq = :seq"
            ),
            {"seq": seq},
        )
    ).first()
    not_found = HTTPException(
        status_code=404, detail={"error": "not_found", "detail": "entry not found"}
    )
    if row is None:
        raise not_found

    buyer_scope = _buyer_scope(claims)
    if buyer_scope is not None and row.buyer_id != buyer_scope:
        raise not_found

    act = claims.act or {}
    # api.md sec 2 "canonical ... for reviewer/operator only (buyer sees payload and
    # hashes, not canonical)"; no stable role string is defined elsewhere (spec.md
    # sec 17 open item), so any non-buyer principal is treated as reviewer/operator-class.
    show_canonical = act.get("type") != "buyer"

    body = _row_to_dict(row)
    body["payload"] = _payload_dict(row.payload)
    body["prev_hash"] = row.prev_hash
    body["row_hash"] = row.row_hash
    if show_canonical:
        body["canonical"] = row.canonical
    return JSONResponse(status_code=200, content=jsonable_encoder(body))
