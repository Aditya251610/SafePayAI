"""POST /mandates/{id}/evaluate's `committed_minor` cumulative-cap enforcement
(spec.md sec 4 step 6) -- previously accepted on the request body but never read by the
handler, so a mandate's cap was only ever checked against a single cart in isolation. Any
number of carts, each individually under the cap, could be approved without limit."""

from __future__ import annotations

import uuid

import pytest

from tests.integration.helpers import preview_and_sign, sample_cart

pytestmark = pytest.mark.asyncio


async def test_committed_minor_reduces_remaining_and_can_trigger_over_cap(
    client, buyer_token, service_token
):
    buyer = buyer_token()
    mandate = await preview_and_sign(
        client, buyer, str(uuid.uuid4()), max_total_minor=6000
    )
    mandate_id = mandate["mandate_id"]

    headers = {"Authorization": f"Bearer {service_token()}"}

    # No prior committed spend: a 2500 cart against a 6000 cap is well within range.
    resp = await client.post(
        f"/mandates/{mandate_id}/evaluate",
        json={"cart": sample_cart(), "committed_minor": 0},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["decision"] == "ALLOW"
    assert body["mandate"]["remaining_minor"] == 6000

    # 4000 already committed via prior checkout orders under this same mandate: the same
    # 2500 cart now pushes cumulative spend to 6500, over the 6000 cap.
    resp = await client.post(
        f"/mandates/{mandate_id}/evaluate",
        json={"cart": sample_cart(), "committed_minor": 4000},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["decision"] == "BLOCK"
    assert body["mandate"]["remaining_minor"] == 2000
    over_cap = next(b for b in body["hard_blocks"] if b["code"] == "OVER_CAP")
    assert over_cap["details"]["remaining_minor"] == 2000


async def test_committed_minor_defaults_to_zero_when_omitted(
    client, buyer_token, service_token
):
    buyer = buyer_token()
    mandate = await preview_and_sign(
        client, buyer, str(uuid.uuid4()), max_total_minor=6000
    )
    mandate_id = mandate["mandate_id"]

    resp = await client.post(
        f"/mandates/{mandate_id}/evaluate",
        json={"cart": sample_cart()},
        headers={"Authorization": f"Bearer {service_token()}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["decision"] == "ALLOW"
    assert body["mandate"]["remaining_minor"] == 6000
