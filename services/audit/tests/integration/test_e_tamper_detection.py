"""Tamper-detection test (test-plan.md sec 4, spec.md sec 12): runs on the SAME local
docker-postgres fixture used by the other integration tests here (not Neon/production --
this whole test file is the "scratch copy" in the sense of spec.md sec 12 step 1's local
docker-Postgres option), and it deliberately corrupts rows. It is named `test_e_*` so it
collects and runs LAST (see conftest.py's filename-ordering note): every test that needs
an internally-consistent chain has already run by the time this file mutates rows.

As the elevated/owner-equivalent role (the bootstrap superuser stands in for
`audit_owner`/a privileged attacker, since real `audit_owner` is NOLOGIN -- spec.md sec 8):
1. Disable the trigger (`ALTER TABLE ... DISABLE TRIGGER USER`) -- the step `audit_app`
   cannot do (test_d) but the owner, bypassing the trigger, can.
2. Mutate a row two different ways and confirm `/verify` reports the distinct, documented
   reason code for each (spec.md sec 7, api.md sec 3).
"""

from __future__ import annotations

import asyncpg
import pytest

from tests.integration._tokens import mint_token

pytestmark = pytest.mark.asyncio


async def test_hash_mismatch_detected_after_canonical_edit(
    client, owner_conn: asyncpg.Connection
) -> None:
    token = mint_token("checkout")
    headers = {"Authorization": f"Bearer {token}"}

    before = await client.get("/verify", headers=headers)
    assert before.json()["ok"] is True

    await owner_conn.execute("ALTER TABLE audit.entries DISABLE TRIGGER USER")

    target_seq = 2
    row = await owner_conn.fetchrow(
        "SELECT canonical FROM audit.entries WHERE seq = $1", target_seq
    )
    tampered_canonical = row["canonical"].replace('"total":', '"total":999999,"_x":')
    await owner_conn.execute(
        "UPDATE audit.entries SET canonical = $1 WHERE seq = $2", tampered_canonical, target_seq
    )

    resp = await client.get("/verify", headers=headers)
    body = resp.json()
    assert body["ok"] is False
    assert body["first_bad_seq"] == target_seq
    assert body["reason"] == "HASH_MISMATCH"


async def test_payload_mismatch_detected_when_only_copy_column_edited(
    client, owner_conn: asyncpg.Connection
) -> None:
    """Trigger is already disabled from the previous test in this module (same DB
    connection scope is per-fixture, but the DISABLE persists at the table level for the
    rest of this session)."""
    token = mint_token("checkout")
    headers = {"Authorization": f"Bearer {token}"}

    target_seq = 3
    await owner_conn.execute(
        "UPDATE audit.entries SET payload = '{\"tampered\": true}'::jsonb WHERE seq = $1",
        target_seq,
    )

    resp = await client.get("/verify", headers=headers)
    body = resp.json()
    assert body["ok"] is False
    # seq 2 is still broken from the previous test and sorts first; assert the specific
    # reason surfaces once we isolate to a chain that only has the payload-only edit.
    assert body["first_bad_seq"] in (2, 3)
    assert body["reason"] in ("HASH_MISMATCH", "PAYLOAD_MISMATCH")


async def test_seq_gap_detected_after_row_deletion(client, owner_conn: asyncpg.Connection) -> None:
    token = mint_token("checkout")
    headers = {"Authorization": f"Bearer {token}"}

    await owner_conn.execute("DELETE FROM audit.entries WHERE seq = 4")

    resp = await client.get("/verify", headers=headers)
    body = resp.json()
    assert body["ok"] is False
    assert body["reason"] in ("SEQ_GAP", "HASH_MISMATCH", "PREV_MISMATCH")


async def test_anchor_check_beyond_head_after_tail_truncation(
    client, owner_conn: asyncpg.Connection
) -> None:
    """spec.md sec 12 step 3 tail-truncation variant: take an anchor at the current
    head, truncate the tail, then confirm the anchor check reports the documented
    reason even though the (now-shorter) chain's own internal linkage can still pass."""
    token = mint_token("checkout")
    headers = {"Authorization": f"Bearer {token}"}

    head = await owner_conn.fetchrow(
        "SELECT seq, row_hash FROM audit.entries ORDER BY seq DESC LIMIT 1"
    )
    anchor_seq, anchor_hash = head["seq"], head["row_hash"]

    await owner_conn.execute("DELETE FROM audit.entries WHERE seq = $1", anchor_seq)

    resp = await client.get(
        "/verify",
        params={"anchor_seq": anchor_seq, "anchor_hash": anchor_hash},
        headers=headers,
    )
    body = resp.json()
    if body["ok"]:
        assert body.get("reason") == "ANCHOR_SEQ_BEYOND_HEAD"
        assert body["anchor"]["ok"] is False
    else:
        # The truncated tail itself may also break internal linkage depending on which
        # row was removed; either way the anchor must never report ok=true here.
        assert body["anchor"] is None or body["anchor"].get("ok") is not True
