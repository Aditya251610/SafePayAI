"""Unit tests for the shared outbox-relay helper (sprint-plan S2-06). No real DB: a fake
AsyncSession stub stands in for Postgres, and the HTTP call to audit is mocked via
httpx.MockTransport -- exactly what the task calls for ("mock the HTTP call to audit").
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from safepayai_common.auth.jwt import ServiceJWTConfig
from safepayai_common.outbox import OutboxRelayConfig, flush_outbox
from safepayai_common.outbox.relay import _row_to_envelope

JWT_CONFIG = ServiceJWTConfig(
    issuer="ps-test",
    audience="audit",
    signing_key_pem="""-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDOaQGfRObwZ9Je
BR/aH+Lk5ZLg3A1UrNg3wG0P/fWIFu+4oXYaWFG42mG5j3pgTzFbbcBN232HUZ1W
bB8oNG0gD+7D8P8WBJaMAGPq7dTYvz6CXKLUHEcxzI+AcrPL4TS1Wmxxzsn6GcOj
NfORKZQs8jpqPsdW4B+4LcUPVWACHgJR7kB1E+z5JPxDkX2+m3iam+IJcNEYZoIq
o/7p2QcVE/ZcrpYxqqEZyf3c3l59ZoiS5K1IuZE4leV5t7J9aULgdHwAhFi7EFoD
j73AjjuUy43/aL9xDYDW7SHRPGDrIdzCBnwWSUplymWzH+KGw8vQZqP34H+vyCbE
HLkjHdarAgMBAAECggEAKLkq6sNrVM8HACm+qQhVeZeZrOd9cdFQL1+1pMwUHy93
SFQCuxvls7TSRwv5tvqo4EL9B99gGsyNYDmgxAvj48mA8AOiMDPjh+ejzvvxXHoO
2SVxsquJmFelkFARDQ53mbgnYSTNUJy4roC8d01ewKdhwwhzx74cQ/gzwtyzPndW
ZxgDsz74aBuSU03PoCchyawME3DYolTh76b4moqEVGYkdB9+pD9FbEq7lZApfxle
JaXJCxa/vw0+4mg9bHfw7QiUBI7hWqNS5Ez/3A5az2FHzZcSyQEKTQvMu5UHge1g
4xyKERFtXiMGJoCmrlsVe19O0VYCMyPUuHsKrxrYoQKBgQDx4XDJV3b3vP3R5EjN
IdqwQdpFEblIUIyU5vbJkEi3aHQUmnm2E/OUsRdZC1H/JHdsf1nwDfliK8phYWEc
8v/Swb6JooHyVfY0FbLwoKNrVTOsr+X0mHYesL9Q8D4VJtcONj1qri79CbA5c7bc
R0VsN6hbX+6tsLtMnw2lO3zjaQKBgQDadYLBdJimDrwVmwjM2KZK9stmGF3sREb5
VMPQTku15dWFIk+/S2mkKBIyIyob921SqWGpnHt3CvQvKiKOUeD0ywK+6DpGNiAt
JLUpIQ+zlbd+0EQFufxVAD4EDTBx4WsuhYAvRWzQwQeEPlNDAsFWKdBqZbfbtvEi
616bU5Tq8wKBgQCD6TuWQmH6F5KhDgt5+7WFHFTKCDFws6UHa7I5GLvfclKkDd7E
orrbY3zlLdxI9f0/KXDGDwjrNhCH7RCGNiu4J7se2oZdv+2mWBMfUavt1Ch7S+5v
51m7wQ6FOI/S/zyXXpM+A8JScx8tJeMa3K+Kpgvl0TqcdN6gmblaXEfuyQKBgQCd
ce3AAYl2vM3fgHHyOP54rq/fMBaZDohccDQEMDmuqiueHSF+jBpiHiMnEWLq7wNS
fRMPC+GL5VAhoetvySEpLBsZfgNp0N6VyovqTZKkanXqJq2vtuBeXqNThjHxEXaO
+9Zru0x2k3gYXlbhx92RfOdhl1fQOWRHN31i0vVT8wKBgAHryNQ/h//GEHEC6YOI
39XBfGix+DN2sNeDq8XAwhXWzOoI+Lk0a509i9UkO8x1D6K8mBlwtqMeSJ+n4GEV
20tU/BhoH5FPPeNm5hvSawdP7cdEXjXIS6JgOyj5ncuZqZne+DpOtdwoIZWA9bEn
5XtHzVssolWzmZ08snVZ+K0i
-----END PRIVATE KEY-----
""",
    kid="test-kid",
)


def _config(**overrides: Any) -> OutboxRelayConfig:
    defaults: dict[str, Any] = dict(
        schema="mandate",
        producer="mandate",
        audit_base_url="http://audit.test",
        jwt=JWT_CONFIG,
        batch_size=100,
    )
    defaults.update(overrides)
    return OutboxRelayConfig(**defaults)


def _row(
    seq: int,
    *,
    event_id: str | None = None,
    event_type: str = "mandate.signed",
    version: int | None = 1,
    aggregate_id: str | None = "agg-1",
    trace_id: str | None = None,
    created_at: datetime | None = None,
    payload: dict | None = None,
) -> dict[str, Any]:
    return {
        "seq": seq,
        "event_id": event_id or str(uuid.uuid4()),
        "type": event_type,
        "version": version,
        "aggregate_id": aggregate_id,
        "payload": payload or {"hello": "world"},
        "trace_id": trace_id,
        "created_at": created_at,
    }


class FakeResult:
    def __init__(self, rows: list[dict] | None = None, scalar_value: Any = None) -> None:
        self._rows = rows or []
        self._scalar_value = scalar_value

    def mappings(self) -> FakeResult:
        return self

    def all(self) -> list[dict]:
        return self._rows

    def scalar(self) -> Any:
        return self._scalar_value


@dataclass
class FakeTxn:
    session: FakeSession

    async def __aenter__(self) -> FakeTxn:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None


@dataclass
class FakeSession:
    """Stands in for AsyncSession: records every statement/params pair it's asked to
    execute and returns pre-scripted results in order, keyed by a substring of the SQL."""

    claim_rows: list[dict] = field(default_factory=list)
    pending_count: int = 0
    executed: list[tuple[str, dict]] = field(default_factory=list)
    updates: list[dict] = field(default_factory=list)

    def begin(self) -> FakeTxn:
        return FakeTxn(self)

    async def execute(self, stmt: Any, params: dict | None = None) -> FakeResult:
        sql = str(stmt)
        params = params or {}
        self.executed.append((sql, params))
        if "FOR UPDATE SKIP LOCKED" in sql:
            return FakeResult(rows=self.claim_rows)
        if "UPDATE" in sql and "attempts = attempts + 1" in sql:
            self.updates.append({"kind": "claim_bump", **params})
            return FakeResult()
        if "UPDATE" in sql and "delivered_to" in sql:
            self.updates.append({"kind": "mark_delivered", **params})
            return FakeResult()
        if "count(*)" in sql:
            return FakeResult(scalar_value=self.pending_count)
        raise AssertionError(f"unexpected statement in FakeSession.execute: {sql}")


def _mock_transport(
    handler: Any,
) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


class TestRowToEnvelope:
    def test_defaults_trace_id_and_version_when_missing(self) -> None:
        row = _row(1, version=None, trace_id=None, created_at=None)
        envelope = _row_to_envelope(row, producer="mandate")
        assert envelope["version"] == 1
        assert envelope["trace_id"]  # generated, non-empty
        assert envelope["producer"] == "mandate"
        assert envelope["actor"] == {
            "type": "system",
            "id": "mandate",
            "auth_method": "service_jwt",
        }
        assert envelope["payload"] == {"hello": "world"}

    def test_preserves_existing_trace_id_and_created_at(self) -> None:
        when = datetime(2026, 1, 1, tzinfo=UTC)
        row = _row(2, trace_id="trace-abc", created_at=when)
        envelope = _row_to_envelope(row, producer="checkout")
        assert envelope["trace_id"] == "trace-abc"
        assert envelope["occurred_at"] == when.isoformat()


async def test_no_pending_rows_is_a_noop() -> None:
    session = FakeSession(claim_rows=[], pending_count=0)
    result = await flush_outbox(session, _config())
    assert (result.delivered, result.failed, result.pending) == (0, 0, 0)
    # No HTTP call attempted and no mark-delivered update issued.
    assert not session.updates


async def test_delivers_appended_and_duplicate_events() -> None:
    eid1, eid2 = str(uuid.uuid4()), str(uuid.uuid4())
    session = FakeSession(
        claim_rows=[_row(10, event_id=eid1), _row(11, event_id=eid2)],
        pending_count=0,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/internal/events/batch"
        assert request.headers["authorization"].startswith("Bearer ")
        return httpx.Response(
            200,
            json={
                "results": [
                    {"event_id": eid1, "status": "APPENDED", "seq": 1},
                    {"event_id": eid2, "status": "DUPLICATE", "seq": 1},
                ]
            },
        )

    async with httpx.AsyncClient(
        transport=_mock_transport(handler), base_url="http://audit.test"
    ) as client:
        result = await flush_outbox(session, _config(), http_client=client)

    assert result.delivered == 2
    assert result.failed == 0
    assert result.pending == 0
    mark_delivered = [u for u in session.updates if u["kind"] == "mark_delivered"]
    assert len(mark_delivered) == 1
    assert set(mark_delivered[0]["seqs"]) == {10, 11}


async def test_audit_unreachable_leaves_rows_pending_not_lost() -> None:
    """ADR-003 / sprint-plan S2-06: "audit down -> events retained and delivered later"."""
    session = FakeSession(claim_rows=[_row(20)], pending_count=1)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    async with httpx.AsyncClient(
        transport=_mock_transport(handler), base_url="http://audit.test"
    ) as client:
        result = await flush_outbox(session, _config(), http_client=client)

    assert result.delivered == 0
    assert result.failed == 1
    assert result.pending == 1
    # The claim step already bumped attempts/next_attempt_at; no mark-delivered call happens.
    assert not any(u["kind"] == "mark_delivered" for u in session.updates)
    assert any(u["kind"] == "claim_bump" for u in session.updates)


async def test_rejected_event_counts_as_failed_not_delivered() -> None:
    eid = str(uuid.uuid4())
    session = FakeSession(claim_rows=[_row(30, event_id=eid)], pending_count=1)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [{"event_id": eid, "status": "REJECTED"}]})

    async with httpx.AsyncClient(
        transport=_mock_transport(handler), base_url="http://audit.test"
    ) as client:
        result = await flush_outbox(session, _config(), http_client=client)

    assert result.delivered == 0
    assert result.failed == 1
    assert not any(u["kind"] == "mark_delivered" for u in session.updates)


async def test_non_200_response_fails_whole_batch() -> None:
    session = FakeSession(claim_rows=[_row(40), _row(41)], pending_count=2)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "db_unavailable"})

    async with httpx.AsyncClient(
        transport=_mock_transport(handler), base_url="http://audit.test"
    ) as client:
        result = await flush_outbox(session, _config(), http_client=client)

    assert result.delivered == 0
    assert result.failed == 2
