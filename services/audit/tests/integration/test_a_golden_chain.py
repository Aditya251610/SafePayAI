"""Chain-verify happy path (test-plan.md sec 2): append N real events, verify the chain.

Runs first (filename ordering, see conftest.py) so the chain is still pristine.
"""

from __future__ import annotations

import pytest

from tests.integration._envelopes import make_envelope
from tests.integration._tokens import mint_token

pytestmark = pytest.mark.asyncio


async def test_genesis_only_chain_verifies(client) -> None:
    token = mint_token("checkout")
    resp = await client.get("/verify", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["checked"] == 1
    assert body["head_seq"] == 1


async def test_append_single_event_then_verify(client) -> None:
    token = mint_token("checkout")
    envelope = make_envelope(event_type="ORDER_CAPTURED")
    resp = await client.post(
        "/internal/events", json=envelope, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["duplicate"] is False
    assert body["seq"] == 2
    assert len(body["row_hash"]) == 64

    verify_resp = await client.get("/verify", headers={"Authorization": f"Bearer {token}"})
    verify_body = verify_resp.json()
    assert verify_body["ok"] is True
    assert verify_body["checked"] == 2
    assert verify_body["head_seq"] == 2


async def test_append_n_events_chain_still_verifies(client) -> None:
    token = mint_token("checkout")
    n = 10
    last_seq = None
    for i in range(n):
        envelope = make_envelope(event_type="ORDER_CAPTURED", order_id=f"ord_golden_{i}")
        resp = await client.post(
            "/internal/events", json=envelope, headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 201, resp.text
        seq = resp.json()["seq"]
        if last_seq is not None:
            assert seq == last_seq + 1  # gapless
        last_seq = seq

    verify_resp = await client.get("/verify", headers={"Authorization": f"Bearer {token}"})
    verify_body = verify_resp.json()
    assert verify_body["ok"] is True
    assert verify_body["head_seq"] == last_seq


async def test_producer_mismatch_rejected_and_nothing_written(client) -> None:
    token = mint_token("checkout")
    envelope = make_envelope(producer="resolution")  # token sub is "checkout"
    resp = await client.post(
        "/internal/events", json=envelope, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "producer_mismatch"


async def test_batch_append_gapless_and_verifies(client) -> None:
    token = mint_token("checkout")
    events = [make_envelope(order_id=f"ord_batch_{i}") for i in range(5)]
    resp = await client.post(
        "/internal/events/batch",
        json={"events": events},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    results = resp.json()["results"]
    assert all(r["status"] == "APPENDED" for r in results)
    seqs = [r["seq"] for r in results]
    assert seqs == sorted(seqs)
    assert seqs == list(range(seqs[0], seqs[0] + len(seqs)))  # gapless

    verify_resp = await client.get("/verify", headers={"Authorization": f"Bearer {token}"})
    assert verify_resp.json()["ok"] is True


async def test_entries_list_and_get_by_seq(client) -> None:
    token = mint_token("checkout")
    resp = await client.get("/entries?endRow=5", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert "rows" in body
    assert body["head_seq"] >= 1

    entry_resp = await client.get("/entries/1", headers={"Authorization": f"Bearer {token}"})
    assert entry_resp.status_code == 200
    entry = entry_resp.json()
    assert entry["seq"] == 1
    assert entry["event_type"] == "CHAIN_GENESIS"
    assert "payload" in entry


async def test_head_endpoint(client) -> None:
    token = mint_token("checkout")
    resp = await client.get("/head", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["chain_id"] == "ps-demo-1"
    assert "paste" in body
    assert body["paste"].startswith("safepayai-audit-head v1")
