"""Real-DB test: /classify with the LLM disabled (kill switch) writes a `triage_log` row
and a `triage.outbox` row in the same transaction (ADR-003), over the runtime role
svc_triage (exercising the grants from 0001_baseline.py, including the outbox sequence
grant), and the idempotency replay path returns the stored result without a second write.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


def _classify_payload(buyer_text: str = "my order never arrived") -> dict:
    return {
        "case_id": str(uuid.uuid4()),
        "trace_id": "trace-1",
        "origin": "buyer_report",
        "buyer_text": buyer_text,
        "timeline": [],
        "order": {
            "order_ref": "ORD-T1",
            "order_date": "2026-09-20",
            "promised_by": "2026-09-28",
            "demo_now": "2026-10-10T09:00:00Z",
            "state": "MONITORING",
            "item_titles": ["Widget"],
        },
    }


@pytest.fixture(autouse=True)
def _override_auth(client):
    # `client` must be a declared dependency, not just an implicit ordering hope: it's the
    # fixture that sets PS_TRIAGEAI_DATABASE_URL before app_triage_ai.main (and transitively app_triage_ai.db/
    # app_triage_ai.settings) is first imported. An autouse fixture with no dependency on `client` can
    # run first and freeze app_triage_ai.settings' module-level singleton with an empty database_url,
    # silently falling back to a credential-less placeholder DSN (asyncpg then defaults to
    # the OS user, not the intended runtime role).
    from app_triage_ai.deps import require_resolution_caller
    from app_triage_ai.main import app

    app.dependency_overrides[require_resolution_caller] = lambda: {"sub": "resolution"}
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _disable_llm(client, monkeypatch: pytest.MonkeyPatch):
    from app_triage_ai.settings import settings

    monkeypatch.setattr(settings, "llm_enabled", False)
    yield


async def test_classify_fail_closed_persists_log_and_outbox(client, db_engine):
    payload = _classify_payload()
    resp = await client.post("/classify", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["route"] == "HUMAN_REVIEW"
    assert body["reasons"] == ["KILL_SWITCH"]

    async with db_engine.connect() as conn:
        log_row = (
            (
                await conn.execute(
                    text(
                        "SELECT case_id, task, route FROM triage.triage_log WHERE case_id = :case_id"
                    ),
                    {"case_id": payload["case_id"]},
                )
            )
            .mappings()
            .first()
        )
        assert log_row is not None
        assert log_row["task"] == "classify"
        assert log_row["route"] == "HUMAN_REVIEW"

        outbox_row = (
            (
                await conn.execute(
                    text(
                        "SELECT type, aggregate_id FROM triage.outbox WHERE aggregate_id = :case_id"
                    ),
                    {"case_id": payload["case_id"]},
                )
            )
            .mappings()
            .first()
        )
        assert outbox_row is not None
        assert outbox_row["type"] == "triage.completed"


async def test_classify_idempotent_replay_does_not_duplicate_log_rows(
    client, db_engine
):
    payload = _classify_payload(buyer_text="replay me please")

    first = await client.post("/classify", json=payload)
    assert first.status_code == 200

    second = await client.post("/classify", json=payload)
    assert second.status_code == 200
    assert second.json()["triage_id"] == first.json()["triage_id"]
    assert second.json()["provenance"]["source"] == "cached"

    async with db_engine.connect() as conn:
        count = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM triage.triage_log WHERE case_id = :case_id AND task = 'classify'"
                ),
                {"case_id": payload["case_id"]},
            )
        ).scalar_one()
        assert count == 1
