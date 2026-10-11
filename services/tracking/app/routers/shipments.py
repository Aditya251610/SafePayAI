"""Shipment endpoints per tracking/api.md. Wave 4: validated stubs, 501 Not Implemented.

The carrier/delivery state machine (LABEL_CREATED -> IN_TRANSIT -> ... ) lives entirely in
our own DB per 00-context-brief.md section 3 (PayPal cannot represent late/lost/delivered).
Real transition logic is Wave 5; this file only validates shape and wires routing/auth deps.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import require_internal_jwt
from app.schemas.shipments import (
    CancelShipmentRequest,
    ShipmentCreateRequest,
    VerifyClaimResponse,
)

router = APIRouter(tags=["shipments"])


def _not_implemented(endpoint: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"{endpoint} pending Wave 5",
    )


@router.post("/shipments", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def create_shipment(
    body: ShipmentCreateRequest,
    claims: dict = Depends(require_internal_jwt),
) -> None:
    raise _not_implemented("POST /shipments")


@router.get("/shipments/{order_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def get_shipments(order_id: str, claims: dict = Depends(require_internal_jwt)) -> None:
    raise _not_implemented("GET /shipments/{order_id}")


@router.get("/shipments/{order_id}/verify", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def verify_claim(
    order_id: str,
    claim: str,
    claims: dict = Depends(require_internal_jwt),
) -> VerifyClaimResponse:
    raise _not_implemented("GET /shipments/{order_id}/verify")


@router.post("/shipments/{shipment_id}/cancel", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def cancel_shipment(
    shipment_id: str,
    body: CancelShipmentRequest,
    claims: dict = Depends(require_internal_jwt),
) -> None:
    raise _not_implemented("POST /shipments/{id}/cancel")
