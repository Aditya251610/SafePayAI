"""Unit tests for app/domain/detector.py (spec s4, s6 - the core late/lost logic)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app_tracking.domain.detector import (
    DetectionKind,
    DetectionThresholds,
    ShipmentFacts,
    detection_event_id,
    evaluate_detections,
    is_late,
    is_lost,
    select_effective_shipment,
    validate_thresholds,
)
from app_tracking.domain.shipment_states import Anomaly, ShipmentStatus

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


def test_validate_thresholds_rejects_lost_after_not_greater_than_late_grace() -> None:
    with pytest.raises(ValueError):
        validate_thresholds(
            DetectionThresholds(
                late_grace_seconds=1000,
                lost_after_seconds=1000,
                lost_after_promise_seconds=2000,
            )
        )


def test_validate_thresholds_rejects_non_positive() -> None:
    with pytest.raises(ValueError):
        validate_thresholds(
            DetectionThresholds(
                late_grace_seconds=0,
                lost_after_seconds=100,
                lost_after_promise_seconds=200,
            )
        )


def test_validate_thresholds_accepts_ordered_values() -> None:
    validate_thresholds(THRESHOLDS)


def test_detection_event_id_is_deterministic() -> None:
    shipment_id = uuid.uuid4()
    a = detection_event_id(shipment_id, DetectionKind.LATE)
    b = detection_event_id(shipment_id, DetectionKind.LATE)
    assert a == b
    assert a != detection_event_id(shipment_id, DetectionKind.LOST)


def test_select_effective_shipment_picks_newest_active() -> None:
    older = _facts(created_at_sim=T0, active=True)
    newer = _facts(created_at_sim=T0 + timedelta(days=1), active=True)
    cancelled_newest = _facts(created_at_sim=T0 + timedelta(days=5), active=False)
    assert select_effective_shipment([older, newer, cancelled_newest]) is newer


def test_select_effective_shipment_none_when_no_active() -> None:
    assert select_effective_shipment([_facts(active=False)]) is None
    assert select_effective_shipment([]) is None


def test_is_late_false_before_grace() -> None:
    facts = _facts()
    assert not is_late(facts, facts.promised_at_sim, THRESHOLDS)


def test_is_late_true_after_grace() -> None:
    facts = _facts()
    sim_now = facts.promised_at_sim + timedelta(
        seconds=THRESHOLDS.late_grace_seconds + 1
    )
    assert is_late(facts, sim_now, THRESHOLDS)


def test_is_late_boundary_exactly_at_grace_is_not_late() -> None:
    facts = _facts()
    sim_now = facts.promised_at_sim + timedelta(seconds=THRESHOLDS.late_grace_seconds)
    assert not is_late(facts, sim_now, THRESHOLDS)


def test_is_late_false_when_delivered() -> None:
    facts = _facts(status=ShipmentStatus.DELIVERED)
    sim_now = facts.promised_at_sim + timedelta(days=365)
    assert not is_late(facts, sim_now, THRESHOLDS)


def test_is_late_false_when_cancelled() -> None:
    facts = _facts(status=ShipmentStatus.CANCELLED)
    sim_now = facts.promised_at_sim + timedelta(days=365)
    assert not is_late(facts, sim_now, THRESHOLDS)


def test_is_lost_true_when_status_lost() -> None:
    facts = _facts(status=ShipmentStatus.LOST)
    assert is_lost(facts, facts.created_at_sim, THRESHOLDS)


def test_is_lost_true_after_last_event_threshold() -> None:
    facts = _facts(last_event_sim=T0)
    sim_now = T0 + timedelta(seconds=THRESHOLDS.lost_after_seconds + 1)
    assert is_lost(facts, sim_now, THRESHOLDS)


def test_is_lost_uses_created_at_sim_when_no_last_event() -> None:
    facts = _facts(last_event_sim=None, created_at_sim=T0)
    sim_now = T0 + timedelta(seconds=THRESHOLDS.lost_after_seconds + 1)
    assert is_lost(facts, sim_now, THRESHOLDS)


def test_is_lost_true_after_promise_threshold() -> None:
    facts = _facts(last_event_sim=T0)
    sim_now = facts.promised_at_sim + timedelta(
        seconds=THRESHOLDS.lost_after_promise_seconds + 1
    )
    assert is_lost(facts, sim_now, THRESHOLDS)


def test_is_lost_false_when_delivered_or_cancelled() -> None:
    for status in (ShipmentStatus.DELIVERED, ShipmentStatus.CANCELLED):
        facts = _facts(status=status)
        sim_now = facts.promised_at_sim + timedelta(days=365)
        assert not is_lost(facts, sim_now, THRESHOLDS)


def test_evaluate_detections_empty_when_on_time() -> None:
    facts = _facts()
    assert evaluate_detections(facts, facts.created_at_sim, THRESHOLDS) == ()


def test_evaluate_detections_empty_when_delivered() -> None:
    facts = _facts(status=ShipmentStatus.DELIVERED)
    sim_now = facts.promised_at_sim + timedelta(days=365)
    assert evaluate_detections(facts, sim_now, THRESHOLDS) == ()


def test_evaluate_detections_late_only() -> None:
    facts = _facts(last_event_sim=T0)
    sim_now = facts.promised_at_sim + timedelta(
        seconds=THRESHOLDS.late_grace_seconds + 1
    )
    candidates = evaluate_detections(facts, sim_now, THRESHOLDS)
    assert [c.kind for c in candidates] == [DetectionKind.LATE]


def test_evaluate_detections_both_late_and_lost_in_order() -> None:
    """Hazard case (spec s4): a jump past both thresholds yields LATE then LOST, in that order."""
    facts = _facts(last_event_sim=T0, created_at_sim=T0)
    sim_now = facts.promised_at_sim + timedelta(
        seconds=THRESHOLDS.lost_after_promise_seconds + 1
    )
    candidates = evaluate_detections(facts, sim_now, THRESHOLDS)
    assert [c.kind for c in candidates] == [DetectionKind.LATE, DetectionKind.LOST]


def test_evaluate_detections_candidate_fields_carry_anomaly() -> None:
    facts = _facts(status=ShipmentStatus.LOST, anomaly=None)
    candidates = evaluate_detections(facts, facts.created_at_sim, THRESHOLDS)
    assert candidates[0].anomaly is None
    assert candidates[0].carrier_status == ShipmentStatus.LOST


def test_evaluate_detections_anomaly_passthrough() -> None:
    facts = _facts(anomaly=Anomaly.DELIVERED_AFTER_PROMISE, last_event_sim=T0)
    sim_now = facts.promised_at_sim + timedelta(
        seconds=THRESHOLDS.late_grace_seconds + 1
    )
    candidates = evaluate_detections(facts, sim_now, THRESHOLDS)
    assert candidates[0].anomaly == Anomaly.DELIVERED_AFTER_PROMISE
