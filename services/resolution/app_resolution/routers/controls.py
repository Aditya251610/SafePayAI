"""REFUNDS_FROZEN kill switch endpoints per resolution/api.md section 3.11.

GET reads `resolution.control_flags` (fail-closed: absent/unreadable = frozen, spec s9).
PUT and POST /refunds/reconcile are wired to the usecases this wave implemented; PUT's
adapter-mirror push (PUT /v1/controls/refunds-frozen on paypal-adapter) is left 501 since that
cross-service push is outside this wave's scope (flagged, not silently skipped).
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app_resolution import repo
from app_resolution.db import get_session
from app_resolution.deps import require_internal_jwt, role_required
from app_resolution.schemas.cases import (
    ReconcileRequest,
    ReconcileResponse,
    RefundsFrozenPutRequest,
    RefundsFrozenState,
)
from app_resolution.usecases.execute_refund import reconcile_attempts

router = APIRouter(tags=["controls"])


def _not_implemented(endpoint: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=f"{endpoint} pending Wave 5"
    )


@router.get("/controls/refunds-frozen")
async def get_refunds_frozen(
    claims: dict = Depends(role_required("operator")),
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


@router.put("/controls/refunds-frozen")
async def put_refunds_frozen(
    body: RefundsFrozenPutRequest,
    claims: dict = Depends(require_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> RefundsFrozenState:
    """api.md section 3.11: operator-only toggle. The adapter-mirror push (PUT
    /v1/controls/refunds-frozen on paypal-adapter, spec s9) is flagged, not silently
    skipped: paypal-adapter's own kill switch (PS_PAYPALADAPTER_MONEY_ENABLED / its own
    control_flags) is independent and must be toggled there separately for now; cross-
    service mirror push with retry-until-ACKED is future work."""
    role = (claims.get("act") or {}).get("role")
    if role != "operator":
        raise HTTPException(status_code=403, detail="ROLE_NOT_ALLOWED")

    set_by = str(claims.get("sub", "operator"))
    epoch = await repo.set_refunds_frozen(
        session, frozen=body.refunds_frozen, reason=body.reason, set_by=set_by
    )
    await repo.insert_outbox_event(
        session,
        event_id=uuid4(),
        event_type="refund.freeze_changed",
        aggregate_id="control_flags",
        payload={
            "refunds_frozen": body.refunds_frozen,
            "epoch": epoch,
            "set_by_role": role,
            "reason_code": body.reason,
        },
    )
    await session.commit()

    flags = await repo.get_control_flags(session)
    assert flags is not None
    return RefundsFrozenState(
        refunds_frozen=flags["refunds_frozen"],
        reason=flags["reason"],
        set_by=flags["set_by"],
        epoch=flags["epoch"],
        readable=True,
        adapter_mirror="PENDING",
    )


@router.post("/refunds/reconcile")
async def reconcile_refunds(
    body: ReconcileRequest,
    claims: dict = Depends(role_required("operator")),
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
