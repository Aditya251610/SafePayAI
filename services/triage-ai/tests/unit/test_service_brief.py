"""Tests for /brief: read-only, field-citation discipline (key_facts built from request
data only, never the model's paraphrase), and gate/fallback behavior. Mocked provider only."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from safepayai_common.llm.gateway import LLMCallResult, LLMFailClosedError, LLMGateway

from app_triage_ai import service
from app_triage_ai.schemas.triage import BriefRequest, OrderFacts, TimelineEvent
from app_triage_ai.settings import Settings

pytestmark = pytest.mark.unit


class FakeProvider:
    def __init__(
        self, result: LLMCallResult | None = None, error: Exception | None = None
    ) -> None:
        self._result = result
        self._error = error

    async def call(
        self, prompt: str, json_schema: dict, timeout_s: float
    ) -> LLMCallResult:
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


def _settings(**overrides: object) -> Settings:
    base = Settings(database_url="postgresql+asyncpg://localhost/x")
    return base.model_copy(update=overrides)


def _order(**overrides: object) -> OrderFacts:
    base = OrderFacts(
        order_ref="ORD-1",
        order_date=date(2026, 9, 20),
        promised_by=date(2026, 9, 28),
        demo_now=datetime(2026, 10, 10, tzinfo=UTC),
        state="HUMAN_REVIEW",
        item_titles=["Widget"],
        amount_minor=2499,
        currency="USD",
    )
    return base.model_copy(update=overrides)


def _request(**overrides: object) -> BriefRequest:
    base = BriefRequest(
        case_id=uuid4(),
        trace_id="t1",
        buyer_text="arrived crushed, box was wet",
        timeline=[
            TimelineEvent(
                event_id="e1",
                ts=datetime(2026, 10, 1, tzinfo=UTC),
                status="DELIVERED",
                note=None,
            )
        ],
        order=_order(),
        triage=None,
        policy_decision="HUMAN_REVIEW",
    )
    return base.model_copy(update=overrides)


async def _run(
    request: BriefRequest, primary: FakeProvider, settings: Settings | None = None
):
    gateway = LLMGateway(primary=primary)
    return await service.brief(request, settings or _settings(), gateway)


async def test_read_only_flag_always_true() -> None:
    primary = FakeProvider(error=LLMFailClosedError("down"))
    response, _ = await _run(_request(), primary)
    assert response.read_only is True


async def test_provider_failure_falls_back_to_code_built_brief() -> None:
    primary = FakeProvider(error=LLMFailClosedError("down"))
    response, _ = await _run(_request(), primary)
    assert response.provenance.source == "template"
    assert any(f.field == "order_ref" for f in response.key_facts)


async def test_amount_key_fact_comes_from_server_data_not_model() -> None:
    primary = FakeProvider(
        result=LLMCallResult(
            valid=True,
            output={
                "summary": "Buyer reports damage.",
                "fact_fields": ["amount"],
                "suggested_flags": [],
                "open_questions": [],
            },
            model_id="m1",
            latency_ms=5,
        )
    )
    response, _ = await _run(_request(), primary)
    amount_fact = next(f for f in response.key_facts if f.field == "amount")
    assert amount_fact.value == "24.99 USD"
    assert amount_fact.source_field == "order.amount_minor"


async def test_summary_with_url_is_gated_to_fallback() -> None:
    primary = FakeProvider(
        result=LLMCallResult(
            valid=True,
            output={
                "summary": "See http://evil.example for the full story.",
                "fact_fields": [],
                "suggested_flags": [],
                "open_questions": [],
            },
            model_id="m1",
            latency_ms=5,
        )
    )
    response, _ = await _run(_request(), primary)
    assert response.provenance.source == "template"


async def test_model_flag_with_unknown_event_id_is_dropped() -> None:
    primary = FakeProvider(
        result=LLMCallResult(
            valid=True,
            output={
                "summary": "Buyer reports damage.",
                "fact_fields": [],
                "suggested_flags": [
                    {"event_ids": ["does-not-exist"], "explanation": "looks odd"}
                ],
                "open_questions": [],
            },
            model_id="m1",
            latency_ms=5,
        )
    )
    response, _ = await _run(_request(), primary)
    model_flags = [f for f in response.inconsistency_flags if f.origin == "model"]
    assert model_flags == []


async def test_model_flag_with_valid_event_id_is_kept_as_info_only() -> None:
    primary = FakeProvider(
        result=LLMCallResult(
            valid=True,
            output={
                "summary": "Buyer reports damage.",
                "fact_fields": [],
                "suggested_flags": [
                    {"event_ids": ["e1"], "explanation": "worth a second look"}
                ],
                "open_questions": [],
            },
            model_id="m1",
            latency_ms=5,
        )
    )
    response, _ = await _run(_request(), primary)
    model_flags = [f for f in response.inconsistency_flags if f.origin == "model"]
    assert len(model_flags) == 1
    assert model_flags[0].severity == "INFO"
    assert model_flags[0].code == "MODEL_SUGGESTED"


async def test_rule_flags_present_even_when_llm_disabled() -> None:
    primary = FakeProvider()
    response, _ = await _run(
        _request(buyer_text="my order never arrived"),
        primary,
        _settings(llm_enabled=False),
    )
    codes = [f.code for f in response.inconsistency_flags]
    assert "CLAIM_NOT_RECEIVED_BUT_DELIVERED" in codes
