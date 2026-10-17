"""Response model for GET /head -- api.md sec 4, spec.md sec 10."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class HeadResponse(BaseModel):
    chain_id: str
    seq: int
    row_hash: str
    count: int
    recorded_at: datetime
    canonical_version: int
    paste: str
    signature: str | None = None
    key_id: str | None = None
