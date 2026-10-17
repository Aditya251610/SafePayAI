"""Response models for GET /verify and /verify/last -- api.md sec 3, spec.md sec 7."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AnchorResult(BaseModel):
    checked: bool
    ok: bool | None = None


class VerifyResponse(BaseModel):
    """Always HTTP 200; `ok` carries the verdict (api.md sec 3)."""

    ok: bool
    chain_id: str | None = None
    checked: int | None = None
    head_seq: int | None = None
    head_hash: str | None = None
    algorithm: str | None = None
    duration_ms: int | None = None
    anchor: AnchorResult | None = None
    # Failure-only fields (reason in: HASH_MISMATCH, PREV_MISMATCH, SEQ_GAP,
    # PAYLOAD_MISMATCH, GENESIS_MISSING, CHAIN_ID_MISMATCH, ANCHOR_HASH_MISMATCH,
    # ANCHOR_SEQ_BEYOND_HEAD).
    first_bad_seq: int | None = None
    reason: str | None = None
    expected: str | None = None
    found: str | None = None


class VerifyLastResponse(BaseModel):
    id: int
    started_at: datetime
    finished_at: datetime | None = None
    head_seq_at_start: int
    ok: bool | None = None
    first_bad_seq: int | None = None
    reason: str | None = None
