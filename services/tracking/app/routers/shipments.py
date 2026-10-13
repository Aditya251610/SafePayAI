"""Shipment endpoints per tracking/api.md. Wired to app/usecases/shipments.py (Wave 5B).

The carrier/delivery state machine (LABEL_CREATED -> IN_TRANSIT -> ... ) lives entirely in
our own DB per 00-context-brief.md section 3 (PayPal cannot represent late/lost/delivered).
"""

from __future__ import annotations

import uuid as uuid_lib

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import repo
from app.db import get_session
from app.deps import require_internal_jwt
from app.domain.demo_clock import sim_now as compute_sim_now
from app.domain.detector import DetectionThresholds, ShipmentFacts
from app.domain.shipment_states import (
    Anomaly,
    IllegalTransition,
    OutcomeProfile,
    ShipmentStatus,
)
from app.domain.verify import VerifyClaim
from app.domain.verify import verify_claim as domain_verify_claim
from app.schemas.shipments import (
    CancelShipmentRequest,
    CancelShipmentResponse,
    ShipmentCreateRequest,
    ShipmentCreateResponse,
    VerifyClaimResponse,
)
from app.settings import settings
from app.usecases.shipments import CreateShipmentCommand
from app.usecases.shipments import cancel_shipment as uc_cancel_shipment
from app.usecases.shipments import create_shipment as uc_create_shipment
from app.usecases.tick import materialize_shipment

router = APIRouter(tags=["shipments"])


def _thresholds() -> DetectionThresholds:
    return DetectionThresholds(
        late_grace_seconds=settings.late_grace_seconds,
        lost_after_seconds=settings.lost_after_seconds,
        lost_after_promise_seconds=settings.lost_after_promise_seconds,
    )


@router.post("/shipments", status_code=201)
async def create_shipment_route(
    body: ShipmentCreateRequest,
    claims: dict = Depends(require_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> ShipmentCreateResponse:
    cmd = CreateShipmentCommand(
        order_id=body.order_id,
        tracking_number=body.tracking_number,
        carrier_name=body.carrier_name,
        outcome_profile=OutcomeProfile(body.outcome_profile),
        actor_sub=str(claims.get("sub", "")),
        idempotency_key=None,
    )
    try:
        result = await uc_create_shipment(session, cmd)
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail="CHECKOUT_UNREACHABLE") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ShipmentCreateResponse(
        id=str(result.shipment_id),
        order_id=result.order_id,
        status=result.status.value,
        promised_at_sim=result.promised_at_sim.isoformat(),
        paypal_sync=result.paypal_sync.value,  # type: ignore[arg-type]
        paypal_tracker_id=result.paypal_tracker_id,
    )


@router.get("/shipments/{order_id}")
async def get_shipments(
    order_id: str,
    claims: dict = Depends(require_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> dict:
    rows = await repo.get_shipments_by_order(session, order_id)
    clock_row = await repo.get_demo_clock_nolock(session)
    sim_now_val = compute_sim_now(repo.now_utc(), clock_row["offset_seconds"])

    for row in rows:
        await materialize_shipment(session, row["id"], sim_now_val)
    await session.commit()

    rows = await repo.get_shipments_by_order(session, order_id)
    delivered = any(r["status"] == ShipmentStatus.DELIVERED.value for r in rows)
    detection_kinds = await repo.get_detection_kinds_for_order(session, order_id)
    return {
        "order_id": order_id,
        "sim_now": sim_now_val.isoformat(),
        "shipments": [
            {
                "id": str(r["id"]),
                "status": r["status"],
                "active": r["active"],
                "promised_at_sim": r["promised_at_sim"].isoformat(),
                "anomaly": r["anomaly"],
            }
            for r in rows
        ],
        "consistency": {
            "delivered": delivered,
            "delivered_at_sim": None,
            "late_detected": "LATE" in detection_kinds,
            "lost_detected": "LOST" in detection_kinds,
        },
        "simulated": True,
        "carrier_label": "SIMULATED CARRIER",
    }


@router.get("/shipments/{order_id}/verify")
async def verify_claim_route(
    order_id: str,
    claim: str,
    claims: dict = Depends(require_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> VerifyClaimResponse:
    try:
        parsed_claim = VerifyClaim(claim)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="INVALID_CLAIM") from exc

    rows = await repo.get_shipments_by_order(session, order_id)
    clock_row = await repo.get_demo_clock_nolock(session)
    sim_now_val = compute_sim_now(repo.now_utc(), clock_row["offset_seconds"])
    for row in rows:
        await materialize_shipment(session, row["id"], sim_now_val)
    await session.commit()
    rows = await repo.get_shipments_by_order(session, order_id)

    active_rows = [r for r in rows if r["active"]]
    effective = (
        max(active_rows, key=lambda r: r["created_at_sim"]) if active_rows else None
    )
    facts = None
    if effective is not None:
        last_event_sim = await repo.get_last_event_sim(session, effective["id"])
        facts = ShipmentFacts(
            shipment_id=effective["id"],
            order_id=effective["order_id"],
            capture_id=effective["capture_id"] or "",
            mandate_id=effective["mandate_id"] or "",
            status=ShipmentStatus(effective["status"]),
            anomaly=Anomaly(effective["anomaly"]) if effective.get("anomaly") else None,
            active=effective["active"],
            created_at_sim=effective["created_at_sim"],
            promised_at_sim=effective["promised_at_sim"],
            last_event_sim=last_event_sim,
            delivered_at_sim=None,
            version=effective["version"],
        )

    outcome = domain_verify_claim(parsed_claim, facts, sim_now_val, _thresholds())
    return VerifyClaimResponse(
        result=outcome.result.value,
        reason_code=outcome.reason_code.value,
        sim_now=sim_now_val.isoformat(),
    )


@router.post("/shipments/{shipment_id}/cancel")
async def cancel_shipment_route(
    shipment_id: str,
    body: CancelShipmentRequest,
    claims: dict = Depends(require_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> CancelShipmentResponse:
    try:
        paypal_sync = await uc_cancel_shipment(
            session,
            uuid_lib.UUID(shipment_id),
            body.reason_code,
            str(claims.get("sub", "")),
        )
    except IllegalTransition as exc:
        raise HTTPException(status_code=409, detail="ILLEGAL_TRANSITION") from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="SHIPMENT_NOT_FOUND") from exc
    return CancelShipmentResponse(status="CANCELLED", paypal_sync=paypal_sync.value)  # type: ignore[arg-type]
