"""Demo-clock simulator endpoints per tracking/api.md + spec.md section 8 (guards, sandbox-only).

Wave 4: stubs. Real guard order (SANDBOX_MODE -> DEMO_CONTROLS_ENABLED -> JWT merchant role ->
body/header checks -> rate limit -> bounds) is Wave 5 business logic.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import require_idempotency_key, require_internal_jwt
from app.schemas.shipments import (
    DemoClockAdvanceRequest,
    DemoClockResetRequest,
    DemoForceShipmentRequest,
)

router = APIRouter(prefix="/demo", tags=["demo"])


def _not_implemented(endpoint: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=f"{endpoint} pending Wave 5")


@router.get("/clock", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def get_clock(claims: dict = Depends(require_internal_jwt)) -> None:
    raise _not_implemented("GET /demo/clock")


@router.post("/clock/advance", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def advance_clock(
    body: DemoClockAdvanceRequest,
    claims: dict = Depends(require_internal_jwt),
    idempotency_key: str = Depends(require_idempotency_key),
) -> None:
    raise _not_implemented("POST /demo/clock/advance")


@router.post("/clock/reset", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def reset_clock(
    body: DemoClockResetRequest,
    claims: dict = Depends(require_internal_jwt),
) -> None:
    raise _not_implemented("POST /demo/clock/reset")


@router.post("/shipments/{shipment_id}/force", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def force_shipment(
    shipment_id: str,
    body: DemoForceShipmentRequest,
    claims: dict = Depends(require_internal_jwt),
) -> None:
    raise _not_implemented("POST /demo/shipments/{id}/force")
