"""Unit tests for app/domain/verify.py (spec s7 claim-consistency rules)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.domain.detector import DetectionThresholds, ShipmentFacts
from app.domain.shipment_states import ShipmentStatus
from app.domain.verify import VerifyClaim, VerifyReasonCode, VerifyResult, verify_claim

THRESHOLDS = DetectionThresholds(
    late_grace_seconds=86400,
    lost_after_seconds=604800,
    lost_after_promise_seconds=1209600,
)
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _facts(**overrides: object) -> ShipmentFacts:
    defaults: dict[str, object] = {
        "shipment_id": uuid.uuid4(),
        "order_id": "order-1",
        "capture_id": "cap-1",
        "mandate_id": "mandate-1",
        "status": ShipmentStatus.IN_TRANSIT,
        "anomaly": None,
        "active": True,
        "created_at_sim": T0,
        "promised_at_sim": T0 + timedelta(days=3),
        "last_event_sim": T0,
        "delivered_at_sim": None,
        "version": 0,
    }
    defaults.update(overrides)
    return ShipmentFacts(**defaults)  # type: ignore[arg-type]


def test_no_shipment_is_insufficient_no_tracking() -> None:
    outcome = verify_claim(VerifyClaim.LATE, None, T0, THRESHOLDS)
    assert outcome.result == VerifyResult.INSUFFICIENT
    assert outcome.reason_code == VerifyReasonCode.NO_TRACKING


def test_lost_claim_contradicted_when_delivered() -> None:
    facts = _facts(status=ShipmentStatus.DELIVERED)
    outcome = verify_claim(VerifyClaim.LOST, facts, T0, THRESHOLDS)
    assert outcome.result == VerifyResult.CONTRADICTED
    assert outcome.reason_code == VerifyReasonCode.CARRIER_SAYS_DELIVERED


def test_not_delivered_claim_contradicted_when_delivered() -> None:
    facts = _facts(status=ShipmentStatus.DELIVERED)
    outcome = verify_claim(VerifyClaim.NOT_DELIVERED, facts, T0, THRESHOLDS)
    assert outcome.result == VerifyResult.CONTRADICTED
    assert outcome.reason_code == VerifyReasonCode.CARRIER_SAYS_DELIVERED


def test_late_claim_contradicted_before_grace() -> None:
    facts = _facts()
    outcome = verify_claim(VerifyClaim.LATE, facts, facts.promised_at_sim, THRESHOLDS)
    assert outcome.result == VerifyResult.CONTRADICTED
    assert outcome.reason_code == VerifyReasonCode.NOT_YET_LATE


def test_late_claim_consistent_after_grace() -> None:
    facts = _facts()
    sim_now = facts.promised_at_sim + timedelta(
        seconds=THRESHOLDS.late_grace_seconds + 1
    )
    outcome = verify_claim(VerifyClaim.LATE, facts, sim_now, THRESHOLDS)
    assert outcome.result == VerifyResult.CONSISTENT
    assert outcome.reason_code == VerifyReasonCode.CONSISTENT_LATE


def test_lost_claim_insufficient_while_in_transit_and_not_past_threshold() -> None:
    facts = _facts(status=ShipmentStatus.IN_TRANSIT, last_event_sim=T0)
    outcome = verify_claim(VerifyClaim.LOST, facts, T0, THRESHOLDS)
    assert outcome.result == VerifyResult.INSUFFICIENT
    assert outcome.reason_code == VerifyReasonCode.NOT_YET_LOST


def test_lost_claim_consistent_when_past_threshold() -> None:
    facts = _facts(last_event_sim=T0)
    sim_now = T0 + timedelta(seconds=THRESHOLDS.lost_after_seconds + 1)
    outcome = verify_claim(VerifyClaim.LOST, facts, sim_now, THRESHOLDS)
    assert outcome.result == VerifyResult.CONSISTENT
    assert outcome.reason_code == VerifyReasonCode.CONSISTENT_LOST
