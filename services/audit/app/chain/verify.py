"""Verify algorithm -- spec.md sec 7.

1. Read head_seq = max(seq) at start (snapshot); all checks bounded by head_seq.
2. Stream rows in seq order in keyset chunks.
3. For each row: (a) seq == expected (gapless; first must be 1 and event_type ==
   CHAIN_GENESIS, prev_hash zeros); (b) prev_hash == previous.row_hash; (c) recompute
   row_hash from canonical, confirm it matches the stored row_hash; (d) parse canonical;
   confirm the `payload` JSONB copy column equals the parsed content's payload; (e)
   chain_id consistent.
4. Return first failure with reason code, or ok with {checked, head_seq, head_hash}.
5. Optional anchor check: row at anchor_seq must have row_hash == anchor_hash; also
   head_seq >= anchor_seq. A chain can be internally consistent (`ok: true`) while the
   anchor check still fails -- spec.md sec 11/12 step C, the documented honest limit
   ("a sophisticated attacker recomputes all hashes after an edit; plain verify PASSES;
   only a pre-edit anchor exposes it"). This module reports that case as `ok=True` with
   `anchor={"checked": True, "ok": False}` and `reason` set to the anchor-specific code,
   matching schemas/verify.py's `VerifyResponse` (both `ok` and `anchor.ok` are carried
   independently; api.md sec 3 ties `reason` to the failure body but doesn't forbid it
   accompanying an anchor-only failure, and the spec explicitly wants this case visible).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.chain.hashing import ALGORITHM_LABEL, GENESIS_PREV_HASH
from app.chain.hashing import row_hash as compute_row_hash

_ENTRY_COLUMNS = (
    "seq, chain_id, event_id, event_type, event_version, producer, occurred_at,"
    " recorded_at, actor_type, actor_id, auth_method, request_id, trace_id, buyer_id,"
    " mandate_id, order_id, case_id, canonical, payload, prev_hash, row_hash"
)


@dataclass
class VerifyResult:
    ok: bool
    chain_id: str | None = None
    checked: int = 0
    head_seq: int = 0
    head_hash: str | None = None
    algorithm: str = ALGORITHM_LABEL
    duration_ms: int = 0
    first_bad_seq: int | None = None
    reason: str | None = None
    expected: str | None = None
    found: str | None = None
    anchor: dict[str, Any] | None = None


def _as_dict(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


async def verify_chain(
    session: AsyncSession,
    *,
    chunk_size: int,
    expected_chain_id: str,
    anchor_seq: int | None = None,
    anchor_hash: str | None = None,
) -> VerifyResult:
    start = time.monotonic()

    def _elapsed_ms() -> int:
        return int((time.monotonic() - start) * 1000)

    head_seq = (
        await session.execute(text("SELECT COALESCE(MAX(seq), 0) FROM entries"))
    ).scalar_one()
    if head_seq == 0:
        return VerifyResult(
            ok=False, reason="GENESIS_MISSING", checked=0, head_seq=0, duration_ms=_elapsed_ms()
        )

    expected_seq = 1
    prev_hash = GENESIS_PREV_HASH
    checked = 0
    last_seq = 0
    head_hash_final: str | None = None
    chain_id_final: str | None = None

    while last_seq < head_seq:
        rows = (
            await session.execute(
                text(
                    f"SELECT {_ENTRY_COLUMNS} FROM entries"
                    " WHERE seq > :last AND seq <= :head ORDER BY seq LIMIT :chunk"
                ),
                {"last": last_seq, "head": head_seq, "chunk": chunk_size},
            )
        ).mappings().all()
        if not rows:
            break

        for row in rows:
            seq = row["seq"]
            if seq != expected_seq:
                return VerifyResult(
                    ok=False, reason="SEQ_GAP", first_bad_seq=seq, checked=checked,
                    head_seq=head_seq, duration_ms=_elapsed_ms(),
                )

            if seq == 1:
                if row["event_type"] != "CHAIN_GENESIS" or row["prev_hash"] != GENESIS_PREV_HASH:
                    return VerifyResult(
                        ok=False, reason="GENESIS_MISSING", first_bad_seq=seq, checked=checked,
                        head_seq=head_seq, duration_ms=_elapsed_ms(),
                    )
            elif row["prev_hash"] != prev_hash:
                return VerifyResult(
                    ok=False, reason="PREV_MISMATCH", first_bad_seq=seq, expected=prev_hash,
                    found=row["prev_hash"], checked=checked, head_seq=head_seq,
                    duration_ms=_elapsed_ms(),
                )

            canonical_text = row["canonical"]
            canonical_bytes = canonical_text.encode("utf-8")
            recomputed = compute_row_hash(row["prev_hash"], canonical_bytes)
            if recomputed != row["row_hash"]:
                return VerifyResult(
                    ok=False, reason="HASH_MISMATCH", first_bad_seq=seq, expected=recomputed,
                    found=row["row_hash"], checked=checked, head_seq=head_seq,
                    duration_ms=_elapsed_ms(),
                )

            try:
                parsed = json.loads(canonical_text)
            except ValueError:
                return VerifyResult(
                    ok=False, reason="HASH_MISMATCH", first_bad_seq=seq, checked=checked,
                    head_seq=head_seq, duration_ms=_elapsed_ms(),
                )

            payload_col = _as_dict(row["payload"])
            if parsed.get("payload") != payload_col:
                return VerifyResult(
                    ok=False, reason="PAYLOAD_MISMATCH", first_bad_seq=seq, checked=checked,
                    head_seq=head_seq, duration_ms=_elapsed_ms(),
                )

            if parsed.get("chain_id") != expected_chain_id or row["chain_id"] != expected_chain_id:
                return VerifyResult(
                    ok=False, reason="CHAIN_ID_MISMATCH", first_bad_seq=seq, checked=checked,
                    head_seq=head_seq, duration_ms=_elapsed_ms(),
                )

            prev_hash = row["row_hash"]
            chain_id_final = row["chain_id"]
            head_hash_final = row["row_hash"]
            checked += 1
            expected_seq += 1
            last_seq = seq

    anchor_info: dict[str, Any] | None = None
    anchor_reason: str | None = None
    if anchor_seq is not None:
        if anchor_seq > head_seq:
            anchor_info = {"checked": True, "ok": False}
            anchor_reason = "ANCHOR_SEQ_BEYOND_HEAD"
        else:
            anchor_row = (
                await session.execute(
                    text("SELECT row_hash FROM entries WHERE seq = :seq"), {"seq": anchor_seq}
                )
            ).first()
            anchor_ok = bool(anchor_row) and anchor_row[0] == anchor_hash
            anchor_info = {"checked": True, "ok": anchor_ok}
            if not anchor_ok:
                anchor_reason = "ANCHOR_HASH_MISMATCH"

    return VerifyResult(
        ok=True,
        chain_id=chain_id_final,
        checked=checked,
        head_seq=head_seq,
        head_hash=head_hash_final,
        duration_ms=_elapsed_ms(),
        anchor=anchor_info,
        reason=anchor_reason,
    )
