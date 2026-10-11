"""REFUNDS_FROZEN kill switch endpoints per resolution/api.md section 3.11.

Wave 4: stub as a settings flag that is CHECKED but routes 501 regardless (per task scope).
Real read/write against `resolution.control_flags` (fail-closed: absent/unreadable = frozen)
is Wave 5. Settings.refunds_frozen_default only seeds the row on first migration and can
never unfreeze an existing one (deployment.md section 7) — that nuance is preserved here by
not exposing a code path that writes `false` without a reason, even in Wave 5 scaffolding.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import require_internal_jwt
from app.schemas.cases import ReconcileRequest, RefundsFrozenPutRequest
from app.settings import settings

router = APIRouter(tags=["controls"])


def _not_implemented(endpoint: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=f"{endpoint} pending Wave 5")


@router.get("/controls/refunds-frozen", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def get_refunds_frozen(claims: dict = Depends(require_internal_jwt)) -> None:
    # Wave 4: the flag is checked (settings.refunds_frozen_default) but the route still 501s;
    # real DB-row read/fail-closed semantics land in Wave 5.
    _ = settings.refunds_frozen_default
    raise _not_implemented("GET /controls/refunds-frozen")


@router.put("/controls/refunds-frozen", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def put_refunds_frozen(
    body: RefundsFrozenPutRequest,
    claims: dict = Depends(require_internal_jwt),
) -> None:
    _ = settings.refunds_frozen_default
    raise _not_implemented("PUT /controls/refunds-frozen")


@router.post("/refunds/reconcile", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def reconcile_refunds(
    body: ReconcileRequest,
    claims: dict = Depends(require_internal_jwt),
) -> None:
    raise _not_implemented("POST /refunds/reconcile")
