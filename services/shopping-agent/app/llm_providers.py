"""Inert provider adapters wired to safepayai_common's LLM gateway INTERFACE (ADR-010).

Wave 4 scope: wire the shape, implement nothing. Real Gemini/Groq SDK calls land in Wave 5.
Do not import a provider SDK here yet.
"""

from __future__ import annotations

from typing import Any

from safepayai_common.llm.gateway import LLMCallResult, LLMFailClosedError, LLMGateway

from app.settings import Settings


class GeminiProvider:
    """Stub primary provider. Raises LLMFailClosedError so callers fail closed per ADR-010."""

    def __init__(self, api_key: str | None, model: str | None) -> None:
        self._api_key = api_key
        self._model = model

    async def call(self, prompt: str, json_schema: dict[str, Any], timeout_s: float) -> LLMCallResult:
        raise NotImplementedError("Gemini provider call not implemented until Wave 5")


class GroqProvider:
    """Stub fallback provider. Raises LLMFailClosedError so callers fail closed per ADR-010."""

    def __init__(self, api_key: str | None, model: str | None) -> None:
        self._api_key = api_key
        self._model = model

    async def call(self, prompt: str, json_schema: dict[str, Any], timeout_s: float) -> LLMCallResult:
        raise NotImplementedError("Groq provider call not implemented until Wave 5")


def build_gateway(settings: Settings) -> LLMGateway:
    """Wired but inert: constructing the gateway never makes a network call."""
    primary = GeminiProvider(settings.gemini_api_key, settings.llm_model_cart)
    fallback = GroqProvider(settings.groq_api_key, settings.llm_model_cart_fallback)
    return LLMGateway(primary=primary, fallback=fallback)


__all__ = ["GeminiProvider", "GroqProvider", "build_gateway", "LLMFailClosedError"]
