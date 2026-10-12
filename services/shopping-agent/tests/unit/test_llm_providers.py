"""Provider adapters: mock the SDK calls (no real API keys, no network) and verify
parsing, the same-provider retry, and fail-closed behavior per ADR-010."""

from __future__ import annotations

import json

import pytest

from app.llm_providers import GeminiProvider, GroqProvider, LLMFailClosedError

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}}


class _FakeGeminiResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeAsyncModels:
    def __init__(self, responses: list) -> None:
        self._responses = list(responses)

    async def generate_content(self, **kwargs):
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _FakeAio:
    def __init__(self, responses: list) -> None:
        self.models = _FakeAsyncModels(responses)


class _FakeGeminiClient:
    def __init__(self, responses: list) -> None:
        self.aio = _FakeAio(responses)


@pytest.mark.asyncio
async def test_gemini_parses_valid_json_response(monkeypatch) -> None:
    from google import genai

    monkeypatch.setattr(
        genai,
        "Client",
        lambda api_key: _FakeGeminiClient([_FakeGeminiResponse('{"ok": true}')]),
    )
    provider = GeminiProvider(api_key="k", model="gemini-flash-lite")
    result = await provider.call("prompt", SCHEMA, timeout_s=2.0)
    assert result.valid is True
    assert result.output == {"ok": True}
    assert result.model_id == "gemini-flash-lite"


@pytest.mark.asyncio
async def test_gemini_retries_once_on_non_json_then_succeeds(monkeypatch) -> None:
    from google import genai

    # Same client instance returned on every call -- the queue must be shared across
    # the retry's second attempt, not reset by constructing a fresh client each time.
    shared_client = _FakeGeminiClient(
        [_FakeGeminiResponse("not json"), _FakeGeminiResponse('{"ok": true}')]
    )
    monkeypatch.setattr(genai, "Client", lambda api_key: shared_client)
    provider = GeminiProvider(api_key="k", model="gemini-flash-lite")
    result = await provider.call("prompt", SCHEMA, timeout_s=2.0)
    assert result.output == {"ok": True}


@pytest.mark.asyncio
async def test_gemini_fails_closed_after_exhausting_retry(monkeypatch) -> None:
    from google import genai

    monkeypatch.setattr(
        genai,
        "Client",
        lambda api_key: _FakeGeminiClient(
            [_FakeGeminiResponse("not json"), _FakeGeminiResponse("still not json")]
        ),
    )
    provider = GeminiProvider(api_key="k", model="gemini-flash-lite")
    with pytest.raises(LLMFailClosedError):
        await provider.call("prompt", SCHEMA, timeout_s=2.0)


@pytest.mark.asyncio
async def test_gemini_never_retries_on_429() -> None:
    class RateLimited(Exception):
        status_code = 429

    class ImmediateFailClient:
        class aio:
            class models:
                @staticmethod
                async def generate_content(**kwargs):
                    raise RateLimited("rate limited")

    provider = GeminiProvider(api_key="k", model="gemini-flash-lite")

    import google.genai as genai_module

    original_client = genai_module.Client
    genai_module.Client = lambda api_key: ImmediateFailClient()
    try:
        with pytest.raises(LLMFailClosedError):
            await provider.call("prompt", SCHEMA, timeout_s=2.0)
    finally:
        genai_module.Client = original_client


@pytest.mark.asyncio
async def test_gemini_missing_config_fails_closed_without_network() -> None:
    provider = GeminiProvider(api_key=None, model=None)
    with pytest.raises(LLMFailClosedError):
        await provider.call("prompt", SCHEMA, timeout_s=2.0)


class _FakeGroqMessage:
    def __init__(self, content: str | None) -> None:
        self.content = content


class _FakeGroqChoice:
    def __init__(self, content: str | None) -> None:
        self.message = _FakeGroqMessage(content)


class _FakeGroqResponse:
    def __init__(self, content: str | None) -> None:
        self.choices = [_FakeGroqChoice(content)]


class _FakeGroqCompletions:
    def __init__(self, responses: list) -> None:
        self._responses = list(responses)

    async def create(self, **kwargs):
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _FakeGroqChat:
    def __init__(self, responses: list) -> None:
        self.completions = _FakeGroqCompletions(responses)


class _FakeGroqClient:
    def __init__(self, responses: list) -> None:
        self.chat = _FakeGroqChat(responses)


@pytest.mark.asyncio
async def test_groq_parses_valid_json_response(monkeypatch) -> None:
    import openai

    monkeypatch.setattr(
        openai,
        "AsyncOpenAI",
        lambda api_key, base_url: _FakeGroqClient(
            [_FakeGroqResponse(json.dumps({"ok": True}))]
        ),
    )
    provider = GroqProvider(api_key="k", model="llama-groq")
    result = await provider.call("prompt", SCHEMA, timeout_s=2.0)
    assert result.output == {"ok": True}


@pytest.mark.asyncio
async def test_groq_retries_once_on_json_validate_failed_400(monkeypatch) -> None:
    import openai

    class JsonValidateFailed(Exception):
        status_code = 400

    shared_client = _FakeGroqClient(
        [
            JsonValidateFailed("json_validate_failed"),
            _FakeGroqResponse(json.dumps({"ok": True})),
        ]
    )
    monkeypatch.setattr(openai, "AsyncOpenAI", lambda api_key, base_url: shared_client)
    provider = GroqProvider(api_key="k", model="llama-groq")
    result = await provider.call("prompt", SCHEMA, timeout_s=2.0)
    assert result.output == {"ok": True}


@pytest.mark.asyncio
async def test_groq_never_retries_on_402(monkeypatch) -> None:
    import openai

    class QuotaExceeded(Exception):
        status_code = 402

    monkeypatch.setattr(
        openai,
        "AsyncOpenAI",
        lambda api_key, base_url: _FakeGroqClient([QuotaExceeded("quota")]),
    )
    provider = GroqProvider(api_key="k", model="llama-groq")
    with pytest.raises(LLMFailClosedError):
        await provider.call("prompt", SCHEMA, timeout_s=2.0)


@pytest.mark.asyncio
async def test_groq_missing_config_fails_closed_without_network() -> None:
    provider = GroqProvider(api_key=None, model=None)
    with pytest.raises(LLMFailClosedError):
        await provider.call("prompt", SCHEMA, timeout_s=2.0)
