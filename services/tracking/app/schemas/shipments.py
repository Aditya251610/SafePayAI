"""Request/response schemas mirroring contracts/openapi/tracking.yaml (api.md section on
POST /shipments etc). Wave 4: schema shapes only; routes still return 501."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ShipmentCreateRequest(BaseModel):
    order_id: str
    tracking_number: str
    carrier_name: str
    outcome_profile: Literal["ON_TIME", "LATE", "LOST", "DELIVERED_AFTER_LATE"] = (
        "ON_TIME"
    )


class ShipmentCreateResponse(BaseModel):
    id: str
    order_id: str
    status: str
    promised_at_sim: str
    paypal_sync: Literal["ADDED", "FAILED", "NOT_ATTEMPTED"]
    paypal_tracker_id: str
    simulated: bool = True
    carrier_label: str = "SIMULATED CARRIER"


class ShipmentEvent(BaseModel):
    seq: int
    to: str
    source: Literal["SCRIPT", "FORCE", "MERCHANT"]
    occurred_at_sim: str


class ShipmentView(BaseModel):
    id: str
    status: str
    active: bool
    promised_at_sim: str
    anomaly: str | None = None
    events: list[ShipmentEvent] = Field(default_factory=list)


class ConsistencyBlock(BaseModel):
    delivered: bool
    delivered_at_sim: str | None = None
    late_detected: bool
    lost_detected: bool


class ShipmentsListResponse(BaseModel):
    order_id: str
    sim_now: str
    shipments: list[ShipmentView] = Field(default_factory=list)
    consistency: ConsistencyBlock
    simulated: bool = True


class VerifyClaimResponse(BaseModel):
    result: Literal["CONSISTENT", "CONTRADICTED", "INSUFFICIENT"]
    reason_code: str
    sim_now: str


class CancelShipmentRequest(BaseModel):
    reason_code: str = "MERCHANT_CANCEL"


class CancelShipmentResponse(BaseModel):
    status: Literal["CANCELLED"]
    paypal_sync: Literal["CANCELLED", "FAILED"]


class DemoClockResponse(BaseModel):
    sim_now: str


class DemoClockAdvanceRequest(BaseModel):
    delta_seconds: int
    reason: str


class TickSummary(BaseModel):
    applied: int = 0
    detected: int = 0
    skipped_lease: bool = False


class DemoClockAdvanceResponse(BaseModel):
    from_sim: str
    to_sim: str
    version: int
    tick: TickSummary


class DemoClockResetRequest(BaseModel):
    reason: str = "DEMO_RESET"


class DemoClockResetResponse(BaseModel):
    offset_seconds: int


class DemoForceShipmentRequest(BaseModel):
    to_status: str
    reason: str


class DemoForceShipmentResponse(BaseModel):
    id: str
    status: str
    source: Literal["FORCE"] = "FORCE"
    tick: TickSummary


class DetectorRunResponse(BaseModel):
    trigger: Literal["manual", "inprocess", "ping", "external"]
    skipped_lease: bool
    applied: int
    detected: int
    sim_now: str


class InternalEventEnvelope(BaseModel):
    event_id: UUID
    type: str
    version: int
    aggregate_id: str
    payload: dict
    trace_id: str | None = None
