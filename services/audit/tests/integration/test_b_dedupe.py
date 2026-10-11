"""Idempotency / duplicate event_id tests (test-plan.md sec 2 "Idempotency/dedup check",
api.md sec 1 200/409 responses).
"""

from __future__ import annotations

import uuid

import pytest

from tests.integration._envelopes import make_envelope
from tests.integration._tokens import mint_token

pytestmark = pytest.mark.asyncio


async def test_duplicate_event_id_is_a_noop(client) -> None:
    token = mint_token("checkout")
    event_id = str(uuid.uuid4())
    envelope = make_envelope(event_id=event_id, order_id="ord_dedupe_1")

    headers = {"Authorization": f"Bearer {token}"}
    first = await client.post("/internal/events", json=envelope, headers=headers)
    assert first.status_code == 201
    first_body = first.json()
    assert first_body["duplicate"] is False

    before = await client.get("/verify", headers=headers)
    checked_before = before.json()["checked"]

    second = await client.post("/internal/events", json=envelope, headers=headers)
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body["duplicate"] is True
    assert second_body["seq"] == first_body["seq"]
    assert second_body["row_hash"] == first_body["row_hash"]

    after = await client.get("/verify", headers=headers)
    checked_after = after.json()["checked"]
    assert checked_after == checked_before  # no new row was written
    assert after.json()["ok"] is True


async def test_same_event_id_different_content_is_conflict(client) -> None:
    token = mint_token("checkout")
    event_id = str(uuid.uuid4())
    envelope = make_envelope(event_id=event_id, order_id="ord_dedupe_2", amount=1000)
    headers = {"Authorization": f"Bearer {token}"}

    first = await client.post("/internal/events", json=envelope, headers=headers)
    assert first.status_code == 201

    conflicting = make_envelope(event_id=event_id, order_id="ord_dedupe_2", amount=9999)
    second = await client.post("/internal/events", json=conflicting, headers=headers)
    assert second.status_code == 409
    assert second.json()["error"] == "event_id_conflict"
