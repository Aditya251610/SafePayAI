"""GET /head -- api.md sec 4, spec.md sec 10.

Signature is Ed25519 over the `paste` string, present only when PS_AUDIT_HEAD_SIGNING_KEY
is configured (spec.md sec 10: "P1", optional). Every call inserts a `head_exports` row
(informational, spec.md sec 2.3).
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app_audit.chain.content import format_ts
from app_audit.db import get_session
from app_audit.deps import ProducerClaims, verify_internal_token
from app_audit.settings import Settings, get_settings

router = APIRouter(tags=["head"])


def _sign_paste(paste: str, signing_key_b64: str) -> str:
    from nacl.signing import SigningKey

    key_bytes = base64.b64decode(signing_key_b64)
    signing_key = SigningKey(key_bytes)
    signature = signing_key.sign(paste.encode("utf-8")).signature
    return base64.b64encode(signature).decode("ascii")


@router.get("/head")
async def get_head(
    claims: ProducerClaims = Depends(verify_internal_token),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    head_query = text("SELECT seq, row_hash, recorded_at FROM entries ORDER BY seq DESC LIMIT 1")
    row = (await session.execute(head_query)).first()
    if row is None:
        return JSONResponse(
            status_code=503,
            content={
                "error": "db_unavailable",
                "detail": "chain not initialized (genesis missing)",
                "request_id": None,
            },
        )

    recorded_at_str = format_ts(row.recorded_at)
    paste = (
        f"safepayai-audit-head v1 chain={settings.chain_id} seq={row.seq} "
        f"hash={row.row_hash} at={recorded_at_str}"
    )

    signature: str | None = None
    key_id: str | None = None
    if settings.head_signing_key:
        signature = _sign_paste(paste, settings.head_signing_key)
        key_id = settings.head_signing_key_id

    act = claims.act or {}
    await session.execute(
        text(
            "INSERT INTO head_exports"
            " (exported_at, seq, row_hash, signature, requested_by_actor_id)"
            " VALUES (:exported_at, :seq, :row_hash, :signature, :actor_id)"
        ),
        {
            "exported_at": datetime.now(UTC),
            "seq": row.seq,
            "row_hash": row.row_hash,
            "signature": signature,
            "actor_id": act.get("id"),
        },
    )
    await session.commit()

    body = {
        "chain_id": settings.chain_id,
        "seq": row.seq,
        "row_hash": row.row_hash,
        "count": row.seq,
        "recorded_at": recorded_at_str,
        "canonical_version": 1,
        "paste": paste,
        "signature": signature,
        "key_id": key_id,
    }
    return JSONResponse(status_code=200, content=jsonable_encoder(body))
