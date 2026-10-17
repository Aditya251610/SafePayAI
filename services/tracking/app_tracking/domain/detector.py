"""Late/lost detection rules, effective-shipment selection, and deterministic detection event ids.

Implements tracking/spec.md section 6 (late/lost rules, delivered-wins, effective shipment),
section 4 (idempotent detections, event_id = uuid5) and config validation C8
(LOST_AFTER > LATE_GRACE).
Pure module: callers pass `sim_now`; nothing here reads a clock, DB or random source.
Scaffold only; every rule body is yours to write.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app_tracking.domain.shipment_states import Anomaly, ShipmentStatus

# Fixed namespace for uuid5(NAMESPACE, f"{shipment_id}:{kind}") (spec s4 item 3).
# Generated once for this project. MUST NEVER CHANGE: changing it breaks consumer dedupe.
DETECTION_NAMESPACE: uuid.UUID = uuid.UUID("6f1c2a9e-4b7d-5e3a-9c21-8d0e4f7a6b15")


class DetectionKind(StrEnum):
    """Kinds of detection row; PK is (shipment_id, kind) (spec s2 detections table)."""

    LATE = "LATE"
    LOST = "LOST"


@dataclass(frozen=True, slots=True)
class DetectionThresholds:
    """Config-driven durations (spec s6, s9). Values are TBD with PM (spec C8)."""

    late_grace_seconds: int  # PS_TRACKING_LATE_GRACE_SECONDS, default 86400 (I)
    lost_after_seconds: int  # PS_TRACKING_LOST_AFTER_SECONDS, default 604800 (I)
    lost_after_promise_seconds: (
        int  # PS_TRACKING_LOST_AFTER_PROMISE_SECONDS, default 1209600 (I)
    )


@dataclass(frozen=True, slots=True)
class ShipmentFacts:
    """Frozen copy of one shipments row plus the last scan time, under the row lock (spec s4, s6)."""

    shipment_id: uuid.UUID
    order_id: str
    capture_id: str
    mandate_id: str
    status: ShipmentStatus
    anomaly: Anomaly | None
    active: bool
    created_at_sim: datetime
    promised_at_sim: datetime
    last_event_sim: datetime | None  # occurred_at_sim of the newest shipment_events row
    delivered_at_sim: datetime | None  # occurred_at_sim of the DELIVERED event, if any
    version: int


@dataclass(frozen=True, slots=True)
class DetectionCandidate:
    """A detection to insert (ON CONFLICT DO NOTHING) plus its outbox payload fields (s4, s6)."""

    shipment_id: uuid.UUID
    kind: DetectionKind
    event_id: uuid.UUID  # detection_event_id(shipment_id, kind)
    detected_at_sim: datetime
    promised_at_sim: datetime
    carrier_status: ShipmentStatus
    anomaly: Anomaly | None


def validate_thresholds(thresholds: DetectionThresholds) -> None:
    """Refuse to boot unless the durations are ordered correctly (spec s6, C8).

    Inputs: thresholds loaded from settings at startup.
    Output: None if valid; raise ValueError otherwise (process must not start).
    Edge cases: LOST_AFTER must be strictly greater than LATE_GRACE; all durations > 0.
    """
    if thresholds.late_grace_seconds <= 0:
        raise ValueError("late_grace_seconds must be > 0")
    if thresholds.lost_after_seconds <= 0:
        raise ValueError("lost_after_seconds must be > 0")
    if thresholds.lost_after_promise_seconds <= 0:
        raise ValueError("lost_after_promise_seconds must be > 0")
    if thresholds.lost_after_seconds <= thresholds.late_grace_seconds:
        raise ValueError(
            "lost_after_seconds must be strictly greater than late_grace_seconds (C8)"
        )


def detection_event_id(shipment_id: uuid.UUID, kind: DetectionKind) -> uuid.UUID:
    """Return uuid5(DETECTION_NAMESPACE, f"{shipment_id}:{kind}") (spec s4 item 3).

    Inputs: shipment id and detection kind. Output: deterministic UUID, same inputs -> same id.
    """
    return uuid.uuid5(DETECTION_NAMESPACE, f"{shipment_id}:{kind}")


def select_effective_shipment(
    shipments: Sequence[ShipmentFacts],
) -> ShipmentFacts | None:
    """Pick the order's effective shipment: the newest active one (spec s6 order-level rule).

    Inputs: all shipments for one order_id (any status).
    Output: newest active ShipmentFacts, or None if there is none.
    Edge cases: older cancelled shipments are ignored; if any active shipment is DELIVERED the
    caller must emit no new detections for the order (spec s6, flagged I for PM).
    """
    active_shipments = [s for s in shipments if s.active]
    if not active_shipments:
        return None
    return max(active_shipments, key=lambda s: s.created_at_sim)


def is_late(
    facts: ShipmentFacts, sim_now: datetime, thresholds: DetectionThresholds
) -> bool:
    """Return True if the shipment is LATE at sim_now (spec s6 LATE rule).

    Rule: status not in {DELIVERED, CANCELLED} AND sim_now > promised_at_sim + late_grace_seconds.
    Inputs: facts (post scheduled-event apply), sim_now, thresholds.
    Output: bool. Edge cases: DELIVERED at or before sim_now suppresses LATE (delivered wins).
    """
    if facts.status in (ShipmentStatus.DELIVERED, ShipmentStatus.CANCELLED):
        return False
    from datetime import timedelta

    return sim_now > facts.promised_at_sim + timedelta(
        seconds=thresholds.late_grace_seconds
    )


def is_lost(
    facts: ShipmentFacts, sim_now: datetime, thresholds: DetectionThresholds
) -> bool:
    """Return True if the shipment is LOST at sim_now (spec s6 LOST rule).

    Rule: status not in {DELIVERED, CANCELLED} AND (status == LOST
          OR sim_now > last_event_sim + lost_after_seconds
          OR sim_now > promised_at_sim + lost_after_promise_seconds).
    Output: bool. Edge cases: last_event_sim may be None (use created_at_sim as the only anchor; I).
    """
    if facts.status in (ShipmentStatus.DELIVERED, ShipmentStatus.CANCELLED):
        return False
    if facts.status == ShipmentStatus.LOST:
        return True

    from datetime import timedelta

    last_event_anchor = facts.last_event_sim or facts.created_at_sim
    if sim_now > last_event_anchor + timedelta(seconds=thresholds.lost_after_seconds):
        return True
    return sim_now > facts.promised_at_sim + timedelta(
        seconds=thresholds.lost_after_promise_seconds
    )


def evaluate_detections(
    facts: ShipmentFacts,
    sim_now: datetime,
    thresholds: DetectionThresholds,
) -> tuple[DetectionCandidate, ...]:
    """Return the detections to insert for one shipment, LATE before LOST (spec s4 hazard, s6).

    Inputs: facts evaluated AFTER scheduled events were applied for this sim_now.
    Output: zero, one or two candidates in that order. A jump past both thresholds yields both.
    Edge cases: DELIVERED at or before sim_now yields an empty tuple; actual idempotency is
    the caller's INSERT ... ON CONFLICT DO NOTHING on detections (spec s4 item 2).
    """
    if facts.status == ShipmentStatus.DELIVERED:
        return ()

    candidates: list[DetectionCandidate] = []
    if is_late(facts, sim_now, thresholds):
        candidates.append(
            DetectionCandidate(
                shipment_id=facts.shipment_id,
                kind=DetectionKind.LATE,
                event_id=detection_event_id(facts.shipment_id, DetectionKind.LATE),
                detected_at_sim=sim_now,
                promised_at_sim=facts.promised_at_sim,
                carrier_status=facts.status,
                anomaly=facts.anomaly,
            )
        )
    if is_lost(facts, sim_now, thresholds):
        candidates.append(
            DetectionCandidate(
                shipment_id=facts.shipment_id,
                kind=DetectionKind.LOST,
                event_id=detection_event_id(facts.shipment_id, DetectionKind.LOST),
                detected_at_sim=sim_now,
                promised_at_sim=facts.promised_at_sim,
                carrier_status=facts.status,
                anomaly=facts.anomaly,
            )
        )
    return tuple(candidates)
