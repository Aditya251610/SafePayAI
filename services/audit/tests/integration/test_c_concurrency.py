"""Concurrent-writer test (test-plan.md sec 3, spec.md sec 3 option B): N parallel
appends with distinct event_ids must produce a gapless, non-forking chain under the
`pg_advisory_xact_lock` design -- this is the whole point of that design, so it is
actually exercised here, not assumed.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from tests.integration._envelopes import make_envelope
from tests.integration._tokens import mint_token

pytestmark = pytest.mark.asyncio

N = 20


async def test_concurrent_appends_are_gapless_and_chain_verifies(client) -> None:
    token = mint_token("checkout")
    headers = {"Authorization": f"Bearer {token}"}

    before_head = (await client.get("/verify", headers=headers)).json()["head_seq"]

    envelopes = [
        make_envelope(event_id=str(uuid.uuid4()), order_id=f"ord_concurrent_{i}") for i in range(N)
    ]

    async def _append(envelope: dict) -> object:
        return await client.post("/internal/events", json=envelope, headers=headers)

    responses = await asyncio.gather(*[_append(e) for e in envelopes])

    seqs = []
    for resp in responses:
        assert resp.status_code == 201, resp.text
        seqs.append(resp.json()["seq"])

    # No duplicate seqs (no fork), and the whole run is gapless.
    assert len(set(seqs)) == N
    seqs_sorted = sorted(seqs)
    assert seqs_sorted == list(range(before_head + 1, before_head + 1 + N))

    verify_resp = await client.get("/verify", headers=headers)
    verify_body = verify_resp.json()
    assert verify_body["ok"] is True
    assert verify_body["head_seq"] == before_head + N


async def test_concurrent_batch_append_also_gapless(client) -> None:
    token = mint_token("checkout")
    headers = {"Authorization": f"Bearer {token}"}

    before_head = (await client.get("/verify", headers=headers)).json()["head_seq"]
    events = [
        make_envelope(event_id=str(uuid.uuid4()), order_id=f"ord_batch_concurrent_{i}")
        for i in range(10)
    ]
    resp = await client.post("/internal/events/batch", json={"events": events}, headers=headers)
    assert resp.status_code == 200
    results = resp.json()["results"]
    seqs = sorted(r["seq"] for r in results)
    assert seqs == list(range(before_head + 1, before_head + 1 + len(events)))

    verify_resp = await client.get("/verify", headers=headers)
    assert verify_resp.json()["ok"] is True
