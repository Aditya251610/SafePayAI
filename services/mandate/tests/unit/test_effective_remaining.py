"""The cap left for a new cart never double-counts spend that is in both ledgers."""

from __future__ import annotations

import pytest

from app_mandate.mandate_logic import effective_remaining_minor


def test_captured_orders_counted_once_not_twice() -> None:
    # live case: $242.00 spent in the mandate ledger AND $242.00 committed in checkout
    assert effective_remaining_minor(50000, 24200, 0, 24200) == 25800


def test_committed_is_a_floor_when_the_ledger_lags() -> None:
    assert effective_remaining_minor(50000, 0, 0, 12000) == 38000


def test_reserved_counts_against_the_cap() -> None:
    assert effective_remaining_minor(50000, 20000, 5900, 0) == 24100


@pytest.mark.parametrize("spent,reserved,committed", [(60000, 0, 0), (0, 0, 60000)])
def test_never_negative(spent: int, reserved: int, committed: int) -> None:
    assert effective_remaining_minor(50000, spent, reserved, committed) == 0
