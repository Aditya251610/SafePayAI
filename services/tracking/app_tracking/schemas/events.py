"""Outbound event envelopes and payloads for shipment.late_detected and shipment.lost_detected.

Implements tracking/api.md "Events" table and spec.md section 6 (payload fields) and section 4
item 3 (event_id is deterministic). Envelope shape per overview section 7:
event_id, type, version, occurred_at, producer, aggregate_id, trace_id, payload.
All models use extra="forbid": no free text, no notes, no tokens (spec s6, threat B8).
"""

from __future__ import annotations

from datetime import datetime
from typing import Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app_tracking.domain.shipment_states import Anomaly, ShipmentStatus

PayloadT = TypeVar("PayloadT", bound=BaseModel)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DetectionPayloadBase(_Strict):
    """Fields shared by both detection payloads (spec s6: 'enums, ids, timestamps' only)."""

    shipment_id: UUID
    order_id: str
    capture_id: str
    mandate_id: str
    promised_at_sim: datetime
    detected_at_sim: datetime
    carrier_status: ShipmentStatus
    anomaly: Anomaly | None = None
    simulated: Literal[True] = True


class LateDetectedPayload(DetectionPayloadBase):
    """Payload for shipment.late_detected (spec s6 payload with kind LATE)."""

    kind: Literal["LATE"] = "LATE"


class LostDetectedPayload(DetectionPayloadBase):
    """Payload for shipment.lost_detected (spec s6 payload with kind LOST)."""

    kind: Literal["LOST"] = "LOST"


class EventEnvelope(_Strict, Generic[PayloadT]):  # noqa: UP046 - py312 PEP 695 syntax not used yet repo-wide
    """Generic outbox envelope; PayloadT is one of the payload models above."""

    event_id: (
        UUID  # for detections: uuid5(DETECTION_NAMESPACE, f"{shipment_id}:{kind}")
    )
    type: Literal["shipment.late_detected", "shipment.lost_detected"]
    version: Literal[1] = 1
    occurred_at: datetime  # real UTC time of the outbox insert
    producer: Literal["tracking"] = "tracking"
    aggregate_id: str  # shipment_id as string
    trace_id: str | None = None
    payload: PayloadT


class ShipmentLateDetectedEvent(EventEnvelope[LateDetectedPayload]):
    """Concrete envelope for shipment.late_detected."""


class ShipmentLostDetectedEvent(EventEnvelope[LostDetectedPayload]):
    """Concrete envelope for shipment.lost_detected."""
