"""Unit tests for app/llm_provider.py's real Gemini/Groq adapters. No real network calls -
the provider SDK clients are monkeypatched. Covers: missing API key fails closed, a
malformed/non-JSON response fails closed, and a well-formed response is returned as a dict
for app/service.py to validate (never trusted as pre-validated here)."""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest
from safepayai_common.llm.gateway import LLMFailClosedError

from app_triage_ai.llm_provider import (
    GeminiProvider,
    GroqProvider,
    _build_provider,
    build_gateway,
)
from app_triage_ai.settings import Settings

pytestmark = pytest.mark.unit


async def test_gemini_fails_closed_without_api_key() -> None:
    provider = GeminiProvider(api_key=None, model="gemini-test")
    with pytest.raises(LLMFailClosedError):
        await provider.call("prompt", {}, timeout_s=1.0)


async def test_groq_fails_closed_without_api_key() -> None:
    provider = GroqProvider(api_key=None, model="groq-test")
    with pytest.raises(LLMFailClosedError):
        await provider.call("prompt", {}, timeout_s=1.0)


async def test_gemini_fails_closed_on_non_json_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        text = "not valid json"

    class FakeModels:
        async def generate_content(self, **kwargs: Any) -> FakeResponse:
            return FakeResponse()

    class FakeAio:
        models = FakeModels()

    class FakeClient:
        def __init__(self, api_key: str) -> None:
            self.aio = FakeAio()

    fake_genai = types.ModuleType("google.genai")
    fake_genai.Client = FakeClient  # type: ignore[attr-defined]
    fake_types = types.ModuleType("google.genai.types")
    fake_types.GenerateContentConfig = lambda **kwargs: kwargs  # type: ignore[attr-defined]
    fake_google = types.ModuleType("google")
    fake_google.genai = fake_genai  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", fake_types)

    provider = GeminiProvider(api_key="fake-key", model="gemini-test")
    with pytest.raises(LLMFailClosedError):
        await provider.call("prompt", {}, timeout_s=1.0)


async def test_gemini_returns_parsed_dict_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        text = '{"category": "LATE", "confidence": 0.9, "injection_suspected": false, "evidence_quote": null}'

    class FakeModels:
        async def generate_content(self, **kwargs: Any) -> FakeResponse:
            return FakeResponse()

    class FakeAio:
        models = FakeModels()

    class FakeClient:
        def __init__(self, api_key: str) -> None:
            self.aio = FakeAio()

    fake_genai = types.ModuleType("google.genai")
    fake_genai.Client = FakeClient  # type: ignore[attr-defined]
    fake_types = types.ModuleType("google.genai.types")
    fake_types.GenerateContentConfig = lambda **kwargs: kwargs  # type: ignore[attr-defined]
    fake_google = types.ModuleType("google")
    fake_google.genai = fake_genai  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", fake_types)

    provider = GeminiProvider(api_key="fake-key", model="gemini-test")
    result = await provider.call("prompt", {}, timeout_s=1.0)
    assert result.valid is True
    assert result.output == {
        "category": "LATE",
        "confidence": 0.9,
        "injection_suspected": False,
        "evidence_quote": None,
    }
    assert result.model_id == "gemini-test"


def test_build_provider_rejects_unknown_name() -> None:
    settings = Settings(database_url="postgresql+asyncpg://localhost/x")
    with pytest.raises(ValueError):
        _build_provider("not-a-real-provider", None, settings)


def test_build_gateway_wires_configured_primary_and_fallback() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://localhost/x",
        llm_provider_primary="groq",
        llm_provider_fallback="gemini",
    )
    gateway = build_gateway(settings)
    assert isinstance(gateway._primary, GroqProvider)
    assert isinstance(gateway._fallback, GeminiProvider)
