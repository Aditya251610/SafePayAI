from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from app_resolution.routers import cases
from app_resolution.schemas.cases import offer_view_from_row


def _offer_row(**kw):
    row = {
        "id": uuid.uuid4(),
        "action": "REFUND",
        "amount_minor": 1250,
        "currency": "USD",
        "tier": "CONFIRM",
        "status": "ACTIVE",
        "proposal_hash": "abc",
        "expires_at": datetime(2030, 1, 1, tzinfo=UTC),
    }
    row.update(kw)
    return row


def test_offer_view_none_when_no_offer() -> None:
    assert offer_view_from_row(None) is None


def test_offer_view_maps_minor_units_currency_tier_expiry() -> None:
    row = _offer_row()
    v = offer_view_from_row(row)
    assert v is not None
    assert (v.offer_id, v.amount_minor, v.currency, v.tier, v.status) == (
        str(row["id"]),
        1250,
        "USD",
        "CONFIRM",
        "ACTIVE",
    )
    assert v.expires_at.startswith("2030-01-01")


async def _call(monkeypatch, *, offer, claims_buyer="b1"):
    case_id = uuid.uuid4()
    case = {
        "id": case_id,
        "order_id": "o1",
        "state": "OFFERED",
        "version": 1,
        "kind": "LATE",
        "origin": "DETECTOR",
        "opened_at": datetime(2030, 1, 1, tzinfo=UTC),
        "window_hold": False,
        "buyer_id": "b1",
    }

    async def get_case(session, cid):
        return case

    async def get_active_offer(session, cid):
        assert cid == case_id
        return offer

    monkeypatch.setattr(cases.repo, "get_case", get_case)
    monkeypatch.setattr(cases.repo, "get_active_offer", get_active_offer)
    claims = {"act": {"role": "buyer"}, "buyer_id": claims_buyer}
    return await cases.get_case_route(str(case_id), claims=claims, session=None)


async def test_case_read_includes_active_offer(monkeypatch) -> None:
    resp = await _call(monkeypatch, offer=_offer_row())
    assert resp.offer is not None and resp.offer.amount_minor == 1250


async def test_case_read_offer_null_when_none(monkeypatch) -> None:
    resp = await _call(monkeypatch, offer=None)
    assert resp.offer is None


async def test_case_read_stays_buyer_scoped(monkeypatch) -> None:
    with pytest.raises(HTTPException) as ei:
        await _call(monkeypatch, offer=_offer_row(), claims_buyer="other")
    assert ei.value.status_code == 404
