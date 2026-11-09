"""Non-UUID path ids are a clean 404, never a Postgres uuid-cast 500."""

from __future__ import annotations

import uuid

import pytest

from app_checkout.deps import valid_cart_id, valid_order_id
from app_checkout.errors import CheckoutError


def test_valid_uuids_pass_through_normalised() -> None:
    raw = str(uuid.uuid4())
    assert valid_order_id(raw.upper()) == raw
    assert valid_cart_id(raw) == raw


@pytest.mark.parametrize("bad", ["None", "preview", "123", ""])
def test_non_uuid_ids_are_404(bad: str) -> None:
    with pytest.raises(CheckoutError) as order_exc:
        valid_order_id(bad)
    assert order_exc.value.status_code == 404
    assert order_exc.value.code == "ORDER_NOT_FOUND"
    with pytest.raises(CheckoutError) as cart_exc:
        valid_cart_id(bad)
    assert (cart_exc.value.status_code, cart_exc.value.code) == (404, "CART_NOT_FOUND")
