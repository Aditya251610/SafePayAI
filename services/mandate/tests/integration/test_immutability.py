"""DB-level immutability: UPDATE on an immutable table via the runtime role
(svc_mandate) must fail at the database, not just be unreachable through the app."""

from __future__ import annotations

import uuid

import asyncpg
import pytest

from tests.integration.helpers import preview_and_sign


async def test_svc_mandate_cannot_update_mandates_row(client, buyer_token, svc_conn):
    mandate = await preview_and_sign(client, buyer_token(), str(uuid.uuid4()))
    with pytest.raises(asyncpg.PostgresError):
        await svc_conn.execute(
            "UPDATE mandate.mandates SET intent_text = 'x' WHERE mandate_id = $1",
            uuid.UUID(mandate["mandate_id"]),
        )


async def test_svc_mandate_cannot_delete_mandates_row(client, buyer_token, svc_conn):
    mandate = await preview_and_sign(client, buyer_token(), str(uuid.uuid4()))
    with pytest.raises(asyncpg.PostgresError):
        await svc_conn.execute(
            "DELETE FROM mandate.mandates WHERE mandate_id = $1", uuid.UUID(mandate["mandate_id"])
        )


async def test_svc_mandate_cannot_change_mandate_spend_ceiling(client, buyer_token, svc_conn):
    mandate = await preview_and_sign(client, buyer_token(), str(uuid.uuid4()))
    with pytest.raises(asyncpg.PostgresError):
        await svc_conn.execute(
            "UPDATE mandate.mandate_spend SET max_total_minor = 1 WHERE mandate_id = $1",
            uuid.UUID(mandate["mandate_id"]),
        )
