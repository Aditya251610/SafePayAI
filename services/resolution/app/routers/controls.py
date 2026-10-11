"""REFUNDS_FROZEN kill switch endpoints per resolution/api.md section 3.11.

GET reads `resolution.control_flags` (fail-closed: absent/unreadable = frozen, spec s9).
PUT and POST /refunds/reconcile are wired to the usecases this wave implemented; PUT's
adapter-mirror push (PUT /v1/controls/refunds-frozen on paypal-adapter) is left 501 since that
cross-service push is outside this wave's scope (flagged, not silently skipped).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import repo
from app.db import get_session
from app.deps import require_internal_jwt
from app.schemas.cases import (
    ReconcileRequest,
    ReconcileResponse,
    RefundsFrozenPutRequest,
    RefundsFrozenState,
)
from app.usecases.execute_refund import reconcile_attempts

router = APIRouter(tags=["controls"])


def _not_implemented(endpoint: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=f"{endpoint} pending Wave 5"
    )


@router.get("/controls/refunds-frozen")
async def get_refunds_frozen(
    claims: dict = Depends(require_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> RefundsFrozenState:
    flags = await repo.get_control_flags(session)
    if flags is None:
        # Absent/unreadable = frozen (spec s9 fail-closed).
        return RefundsFrozenState(
            refunds_frozen=True, readable=False, adapter_mirror="PENDING"
        )
    return RefundsFrozenState(
        refunds_frozen=flags["refunds_frozen"],
        reason=flags["reason"],
        set_by=flags["set_by"],
        epoch=flags["epoch"],
        readable=True,
        adapter_mirror="PENDING",
    )


@router.put("/controls/refunds-frozen", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def put_refunds_frozen(
    body: RefundsFrozenPutRequest,
    claims: dict = Depends(require_internal_jwt),
) -> None:
    # Flagged, not silently skipped: the adapter-mirror push (PUT /v1/controls/refunds-frozen
    # on paypal-adapter, spec s9) needs retry-until-ACKED plumbing this wave did not build.
    raise _not_implemented("PUT /controls/refunds-frozen")


@router.post("/refunds/reconcile")
async def reconcile_refunds(
    body: ReconcileRequest,
    claims: dict = Depends(require_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> ReconcileResponse:
    summary = await reconcile_attempts(session, body.limit)
    await session.commit()
    return ReconcileResponse(
        examined=summary.examined,
        finalized_completed=summary.finalized_completed,
        finalized_failed=summary.finalized_failed,
        still_unknown=summary.still_unknown,
        needs_review=summary.needs_review,
        frozen_skipped_replays=summary.frozen_skipped_replays,
    )
