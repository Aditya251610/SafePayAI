"""Stub provider adapters wired to libs/common's LLMGateway interface (ADR-010).

Wave 4 scope: these classes implement the `LLMProvider` Protocol shape but raise
NotImplementedError on every call — wired, inert. NO Gemini/Groq SDK calls live here; that
is Wave 5. Do not import `google.genai` or `groq` in this file yet.
"""

from __future__ import annotations

from typing import Any

from safepayai_common.llm.gateway import LLMCallResult, LLMFailClosedError, LLMGateway


class GroqProviderStub:
    """Primary provider per deployment.md section 3 (Groq gpt-oss-20b for classify).
    Wave 5 will call the real Groq SDK; for now every call fails closed."""

    model_id = "groq-stub"

    async def call(self, prompt: str, json_schema: dict[str, Any], timeout_s: float) -> LLMCallResult:
        raise NotImplementedError("GroqProviderStub.call: provider SDK wiring is Wave 5")


class GeminiProviderStub:
    """Fallback provider per deployment.md section 3 (Gemini Flash-Lite / Flash).
    Wave 5 will call the real Gemini SDK; for now every call fails closed."""

    model_id = "gemini-stub"

    async def call(self, prompt: str, json_schema: dict[str, Any], timeout_s: float) -> LLMCallResult:
        raise NotImplementedError("GeminiProviderStub.call: provider SDK wiring is Wave 5")


def build_gateway() -> LLMGateway:
    """Wires the shared LLMGateway with inert stub providers. Callers MUST catch
    LLMFailClosedError (or NotImplementedError in this Wave-4 stub state) and fall back to
    their restrictive default — never to a money decision (ADR-010)."""
    return LLMGateway(primary=GroqProviderStub(), fallback=GeminiProviderStub())


__all__ = ["GroqProviderStub", "GeminiProviderStub", "build_gateway", "LLMFailClosedError"]
