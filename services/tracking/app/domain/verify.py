"""Claim-consistency types and the verify_claim rule used by GET /shipments/{order_id}/verify.

Implements tracking/spec.md section 7 (consistency checks) and api.md
GET /shipments/{order_id}/verify.
Resolution consumes the result but never trusts it alone (spec s7 last bullet). Pure module.
Scaffold only; the verify_claim body is yours to write.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain.detector import DetectionThresholds, ShipmentFacts


class VerifyClaim(StrEnum):
    """Claims accepted by ?claim= (api.md). Anything else is a 400."""

    LATE = "LATE"
    LOST = "LOST"
    NOT_DELIVERED = "NOT_DELIVERED"


class VerifyResult(StrEnum):
    """Three-valued answer (spec s7). INSUFFICIENT is never treated as a pass by resolution."""

    CONSISTENT = "CONSISTENT"
    CONTRADICTED = "CONTRADICTED"
    INSUFFICIENT = "INSUFFICIENT"


class VerifyReasonCode(StrEnum):
    """Stable reason codes returned with a verify result (spec s7, api.md)."""

    CARRIER_SAYS_DELIVERED = "CARRIER_SAYS_DELIVERED"
    NOT_YET_LATE = "NOT_YET_LATE"
    NOT_YET_LOST = (
        "NOT_YET_LOST"  # name not in spec; spec s7 only says INSUFFICIENT (I)
    )
    NO_TRACKING = "NO_TRACKING"
    CONSISTENT_LATE = "CONSISTENT_LATE"  # not in spec; positive reason code (I)
    CONSISTENT_LOST = "CONSISTENT_LOST"  # not in spec; positive reason code (I)


@dataclass(frozen=True, slots=True)
class VerifyOutcome:
    """Body of the verify endpoint (api.md), before adding sim_now."""

    result: VerifyResult
    reason_code: VerifyReasonCode


def verify_claim(
    claim: VerifyClaim,
    shipment: ShipmentFacts | None,
    sim_now: datetime,
    thresholds: DetectionThresholds,
) -> VerifyOutcome:
    """Check a buyer/resolution claim against our own shipment facts (spec s7 rules).

    Inputs: claim, the effective shipment (None if the order has no shipment), sim_now, thresholds.
    Output: VerifyOutcome.
    Rules (spec s7):
      - LOST or NOT_DELIVERED while DELIVERED -> CONTRADICTED / CARRIER_SAYS_DELIVERED.
      - LATE before promised_at_sim + late_grace -> CONTRADICTED / NOT_YET_LATE.
      - LOST while IN_TRANSIT and not past LOST threshold -> INSUFFICIENT / NOT_YET_LOST.
      - No shipment for a captured order -> INSUFFICIENT / NO_TRACKING.
    Edge cases: caller must run lazy catch-up (materialize) before calling this (spec s5 item 3).
    """
    from app.domain.detector import is_lost
    from app.domain.shipment_states import ShipmentStatus

    if shipment is None:
        return VerifyOutcome(
            result=VerifyResult.INSUFFICIENT, reason_code=VerifyReasonCode.NO_TRACKING
        )

    if (
        claim in (VerifyClaim.LOST, VerifyClaim.NOT_DELIVERED)
        and shipment.status == ShipmentStatus.DELIVERED
    ):
        return VerifyOutcome(
            result=VerifyResult.CONTRADICTED,
            reason_code=VerifyReasonCode.CARRIER_SAYS_DELIVERED,
        )

    if claim == VerifyClaim.LATE:
        from datetime import timedelta

        if shipment.status == ShipmentStatus.DELIVERED:
            return VerifyOutcome(
                result=VerifyResult.CONTRADICTED,
                reason_code=VerifyReasonCode.CARRIER_SAYS_DELIVERED,
            )
        if sim_now <= shipment.promised_at_sim + timedelta(
            seconds=thresholds.late_grace_seconds
        ):
            return VerifyOutcome(
                result=VerifyResult.CONTRADICTED,
                reason_code=VerifyReasonCode.NOT_YET_LATE,
            )
        return VerifyOutcome(
            result=VerifyResult.CONSISTENT, reason_code=VerifyReasonCode.CONSISTENT_LATE
        )

    if claim in (VerifyClaim.LOST, VerifyClaim.NOT_DELIVERED):
        if is_lost(shipment, sim_now, thresholds):
            return VerifyOutcome(
                result=VerifyResult.CONSISTENT,
                reason_code=VerifyReasonCode.CONSISTENT_LOST,
            )
        return VerifyOutcome(
            result=VerifyResult.INSUFFICIENT, reason_code=VerifyReasonCode.NOT_YET_LOST
        )

    return VerifyOutcome(
        result=VerifyResult.INSUFFICIENT, reason_code=VerifyReasonCode.NO_TRACKING
    )
