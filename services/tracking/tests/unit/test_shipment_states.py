"""Unit tests for app/domain/shipment_states.py (spec s2 transition table)."""

from __future__ import annotations

import pytest

from app.domain.shipment_states import (
    IllegalTransition,
    ShipmentStatus,
    TransitionSource,
    is_legal_transition,
)


def test_initial_insert_requires_label_created() -> None:
    assert is_legal_transition(
        None, ShipmentStatus.LABEL_CREATED, TransitionSource.MERCHANT
    )
    assert not is_legal_transition(
        None, ShipmentStatus.IN_TRANSIT, TransitionSource.MERCHANT
    )


@pytest.mark.parametrize(
    "from_status,to_status",
    [
        (ShipmentStatus.LABEL_CREATED, ShipmentStatus.IN_TRANSIT),
        (ShipmentStatus.LABEL_CREATED, ShipmentStatus.CANCELLED),
        (ShipmentStatus.IN_TRANSIT, ShipmentStatus.OUT_FOR_DELIVERY),
        (ShipmentStatus.IN_TRANSIT, ShipmentStatus.EXCEPTION),
        (ShipmentStatus.IN_TRANSIT, ShipmentStatus.LOST),
        (ShipmentStatus.IN_TRANSIT, ShipmentStatus.DELIVERED),
        (ShipmentStatus.IN_TRANSIT, ShipmentStatus.CANCELLED),
        (ShipmentStatus.OUT_FOR_DELIVERY, ShipmentStatus.DELIVERED),
        (ShipmentStatus.OUT_FOR_DELIVERY, ShipmentStatus.EXCEPTION),
        (ShipmentStatus.EXCEPTION, ShipmentStatus.IN_TRANSIT),
        (ShipmentStatus.EXCEPTION, ShipmentStatus.LOST),
        (ShipmentStatus.EXCEPTION, ShipmentStatus.DELIVERED),
    ],
)
def test_legal_script_edges(
    from_status: ShipmentStatus, to_status: ShipmentStatus
) -> None:
    assert is_legal_transition(from_status, to_status, TransitionSource.SCRIPT)


def test_delivered_and_cancelled_are_terminal() -> None:
    for to_status in ShipmentStatus:
        assert not is_legal_transition(
            ShipmentStatus.DELIVERED, to_status, TransitionSource.SCRIPT
        )
        assert not is_legal_transition(
            ShipmentStatus.CANCELLED, to_status, TransitionSource.SCRIPT
        )


def test_lost_to_delivered_requires_script_or_force() -> None:
    assert is_legal_transition(
        ShipmentStatus.LOST, ShipmentStatus.DELIVERED, TransitionSource.SCRIPT
    )
    assert is_legal_transition(
        ShipmentStatus.LOST, ShipmentStatus.DELIVERED, TransitionSource.FORCE
    )
    assert not is_legal_transition(
        ShipmentStatus.LOST, ShipmentStatus.DELIVERED, TransitionSource.MERCHANT
    )


def test_lost_to_cancelled_is_legal() -> None:
    assert is_legal_transition(
        ShipmentStatus.LOST, ShipmentStatus.CANCELLED, TransitionSource.MERCHANT
    )


def test_illegal_edge_rejected() -> None:
    assert not is_legal_transition(
        ShipmentStatus.LABEL_CREATED, ShipmentStatus.DELIVERED, TransitionSource.SCRIPT
    )


def test_illegal_transition_is_an_exception_type() -> None:
    assert issubclass(IllegalTransition, Exception)
