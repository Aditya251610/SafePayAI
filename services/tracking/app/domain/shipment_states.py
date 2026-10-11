"""Shipment carrier-state enums, legal-transition table, and PayPal-sync/anomaly types for tracking.

Implements tracking/spec.md section 2 (carrier-status state machine), section 1 (PayPal sync
enum) and section 6 (anomaly flags). Pure module: no FastAPI, SQLAlchemy, httpx, clock or
randomness imports. Scaffold only; the transition check body is yours to write.
"""

from __future__ import annotations

from enum import StrEnum


class ShipmentStatus(StrEnum):
    """Carrier-side status of one shipment (spec s2). 'Late' is NOT a status (derived, s6)."""

    LABEL_CREATED = "LABEL_CREATED"
    IN_TRANSIT = "IN_TRANSIT"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    EXCEPTION = "EXCEPTION"
    LOST = "LOST"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class TransitionSource(StrEnum):
    """Who caused an applied transition; stored on every shipment_events row (spec s2)."""

    SCRIPT = "SCRIPT"
    FORCE = "FORCE"
    MERCHANT = "MERCHANT"


class Anomaly(StrEnum):
    """Flags attached to a shipment, never to a detection by themselves (spec s6, s7)."""

    LOST_THEN_DELIVERED = "LOST_THEN_DELIVERED"
    DELIVERED_AFTER_PROMISE = "DELIVERED_AFTER_PROMISE"


class PaypalSync(StrEnum):
    """PayPal tracker signal only, never a decision input (spec s1, V)."""

    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    ADDED = "ADDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class OutcomeProfile(StrEnum):
    """Scripted outcome at shipment creation; sandbox-only override (spec s2, api POST /shipments)."""

    ON_TIME = "ON_TIME"
    LATE = "LATE"
    LOST = "LOST"
    DELIVERED_AFTER_LATE = "DELIVERED_AFTER_LATE"


# Statuses with no further carrier transitions for LATE/LOST evaluation (spec s6).
# LOST is intentionally NOT here: LOST -> DELIVERED and LOST -> CANCELLED are still legal.
TERMINAL_STATUSES: frozenset[ShipmentStatus] = frozenset(
    {ShipmentStatus.DELIVERED, ShipmentStatus.CANCELLED}
)

# Legal carrier transitions (spec s2 table). Any non-terminal status may also go to CANCELLED
# (merchant cancel); that edge is listed explicitly below. LOST -> DELIVERED is ONLY reachable
# via the force/script path `DELIVERED_AFTER_LOST`, which must also set anomaly=LOST_THEN_DELIVERED.
SHIPMENT_TRANSITIONS: dict[ShipmentStatus, frozenset[ShipmentStatus]] = {
    ShipmentStatus.LABEL_CREATED: frozenset(
        {ShipmentStatus.IN_TRANSIT, ShipmentStatus.CANCELLED}
    ),
    ShipmentStatus.IN_TRANSIT: frozenset(
        {
            ShipmentStatus.OUT_FOR_DELIVERY,
            ShipmentStatus.EXCEPTION,
            ShipmentStatus.LOST,
            ShipmentStatus.DELIVERED,
            ShipmentStatus.CANCELLED,
        }
    ),
    ShipmentStatus.OUT_FOR_DELIVERY: frozenset(
        {ShipmentStatus.DELIVERED, ShipmentStatus.EXCEPTION, ShipmentStatus.CANCELLED}
    ),
    ShipmentStatus.EXCEPTION: frozenset(
        {
            ShipmentStatus.IN_TRANSIT,
            ShipmentStatus.LOST,
            ShipmentStatus.DELIVERED,
            ShipmentStatus.CANCELLED,
        }
    ),
    ShipmentStatus.LOST: frozenset(
        {ShipmentStatus.DELIVERED, ShipmentStatus.CANCELLED}
    ),
    ShipmentStatus.DELIVERED: frozenset(),
    ShipmentStatus.CANCELLED: frozenset(),
}

# Special-case edge: LOST -> DELIVERED. Allowed only when source == FORCE or SCRIPT with the
# DELIVERED_AFTER_LOST marker; the caller must set anomaly=LOST_THEN_DELIVERED in the same tx.
DELIVERED_AFTER_LOST_EDGE: tuple[ShipmentStatus, ShipmentStatus] = (
    ShipmentStatus.LOST,
    ShipmentStatus.DELIVERED,
)


class IllegalTransition(Exception):
    """Raised for a transition not in SHIPMENT_TRANSITIONS; maps to HTTP 409 ILLEGAL_TRANSITION."""


def is_legal_transition(
    from_status: ShipmentStatus | None,
    to_status: ShipmentStatus,
    source: TransitionSource,
) -> bool:
    """Return True if moving from_status -> to_status is allowed for this source.

    Inputs: from_status is None for the initial LABEL_CREATED insert (spec s2 row 1).
    Output: bool; caller raises IllegalTransition on False.
    Edge cases: DELIVERED/CANCELLED have no outgoing edges; LOST -> DELIVERED requires
    source in {SCRIPT, FORCE} plus the DELIVERED_AFTER_LOST marker (spec s2, s8).
    """
    if from_status is None:
        return to_status == ShipmentStatus.LABEL_CREATED

    if (from_status, to_status) == DELIVERED_AFTER_LOST_EDGE:
        return source in (TransitionSource.SCRIPT, TransitionSource.FORCE)

    return to_status in SHIPMENT_TRANSITIONS.get(from_status, frozenset())
