"""Response models for GET /entries, /entries/{seq}, /entries/by-ref -- api.md sec 2."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class VerifiedSummary(BaseModel):
    ok: bool
    head_seq: int
    at: datetime


class EntryRow(BaseModel):
    seq: int
    recorded_at: datetime
    event_type: str
    actor_type: str
    actor_id: str
    auth_method: str
    request_id: str
    mandate_id: str | None = None
    order_id: str | None = None
    case_id: str | None = None
    summary: str
    row_hash_short: str
    prev_hash_short: str


class EntriesResponse(BaseModel):
    rows: list[EntryRow]
    lastRow: int
    head_seq: int
    verified: VerifiedSummary | None = None


class EntryDetail(EntryRow):
    payload: dict[str, Any]
    prev_hash: str
    row_hash: str
    canonical: str | None = None
