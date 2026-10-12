"""Real Gemini/Groq provider adapters wired to safepayai_common's LLMGateway interface
(ADR-010). Per llm-integration-spec.md section 1: Gemini via `google-genai`
(`from google import genai`), Groq via the `openai` SDK pointed at Groq's OpenAI-compatible
base_url (Groq's API is OpenAI-compatible; no reason found in research to prefer Groq's own
thinner SDK wrapper).

Deliberate simplifications vs. the full spec (time-boxed for this wave, not a safety gap):
- No same-provider retry-once-on-timeout/5xx (llm-integration-spec.md section 3). Every
  failure here raises `LLMFailClosedError` immediately so `LLMGateway` falls over to the
  configured fallback provider once; the caller (app/service.py) then fails closed to its
  restrictive default if that also fails. This is strictly MORE conservative than the full
  spec, never less safe - it just burns the fallback hop slightly more eagerly.
- `response_schema` is NOT passed to Gemini alongside `response_mime_type="application/json"`
  (llm-integration-spec.md section 2's "both together give a hard guarantee" recommendation).
  Rationale: our pydantic-generated JSON Schemas carry `$defs`/`additionalProperties`, which
  Google's own docs warn can trigger a 400 on complex schemas - and the architecture's own
  standing rule is "native structured-output mode is NOT trusted as the validator anyway,
  always re-validate with pydantic" (agent-and-mcp-design.md section 0), which this module's
  caller (app/service.py, via app/llm_io.py) always does. Passing only the MIME-type hint and
  re-validating strictly is the documented fallback path, not a shortcut around validation.
- Groq uses `response_format={"type": "json_object"}` (broadly supported) rather than the
  newer `json_schema` strict mode, for the same reason.
Both choices are safe specifically because NOTHING downstream trusts provider-native
"valid JSON" claims - `LLMCallResult.valid=True` here means "we got a JSON object back",
not "this is schema-correct"; strict pydantic validation happens in app/service.py.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from safepayai_common.llm.gateway import LLMCallResult, LLMFailClosedError, LLMGateway

from app.settings import Settings

_DEFAULT_GEMINI_MODEL = "gemini-2.0-flash-lite"
_DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"


class GeminiProvider:
    """Real Gemini provider via `google-genai`'s async client."""

    def __init__(self, api_key: str | None, model: str | None) -> None:
        self._api_key = api_key
        self._model = model or _DEFAULT_GEMINI_MODEL

    async def call(
        self, prompt: str, json_schema: dict[str, Any], timeout_s: float
    ) -> LLMCallResult:
        if not self._api_key:
            raise LLMFailClosedError("PS_TRIAGEAI_GEMINI_API_KEY not configured")

        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:  # pragma: no cover - dependency always declared
            raise LLMFailClosedError(f"google-genai not installed: {exc}") from exc

        started = time.monotonic()
        client = genai.Client(api_key=self._api_key)
        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.0,
                    ),
                ),
                timeout=timeout_s,
            )
        except TimeoutError as exc:
            raise LLMFailClosedError(f"gemini call timed out: {exc}") from exc
        except Exception as exc:
            raise LLMFailClosedError(f"gemini call failed: {exc}") from exc

        latency_ms = int((time.monotonic() - started) * 1000)
        text = getattr(response, "text", None)
        if not text:
            raise LLMFailClosedError("gemini returned an empty response")
        try:
            output = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMFailClosedError(f"gemini returned non-JSON output: {exc}") from exc
        if not isinstance(output, dict):
            raise LLMFailClosedError("gemini returned a non-object JSON value")
        return LLMCallResult(
            valid=True, output=output, model_id=self._model, latency_ms=latency_ms
        )


class GroqProvider:
    """Real Groq provider via the `openai` SDK pointed at Groq's OpenAI-compatible endpoint."""

    def __init__(self, api_key: str | None, model: str | None) -> None:
        self._api_key = api_key
        self._model = model or _DEFAULT_GROQ_MODEL

    async def call(
        self, prompt: str, json_schema: dict[str, Any], timeout_s: float
    ) -> LLMCallResult:
        if not self._api_key:
            raise LLMFailClosedError("PS_TRIAGEAI_GROQ_API_KEY not configured")

        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover - dependency always declared
            raise LLMFailClosedError(f"openai sdk not installed: {exc}") from exc

        started = time.monotonic()
        client = AsyncOpenAI(
            api_key=self._api_key, base_url="https://api.groq.com/openai/v1"
        )
        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0.0,
                ),
                timeout=timeout_s,
            )
        except TimeoutError as exc:
            raise LLMFailClosedError(f"groq call timed out: {exc}") from exc
        except Exception as exc:
            raise LLMFailClosedError(f"groq call failed: {exc}") from exc

        latency_ms = int((time.monotonic() - started) * 1000)
        choices = getattr(response, "choices", None) or []
        content = choices[0].message.content if choices else None
        if not content:
            raise LLMFailClosedError("groq returned an empty response")
        try:
            output = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMFailClosedError(f"groq returned non-JSON output: {exc}") from exc
        if not isinstance(output, dict):
            raise LLMFailClosedError("groq returned a non-object JSON value")
        model_id = getattr(response, "model", None) or self._model
        return LLMCallResult(
            valid=True, output=output, model_id=model_id, latency_ms=latency_ms
        )


def _build_provider(
    name: str, model: str | None, settings: Settings
) -> GeminiProvider | GroqProvider:
    if name == "gemini":
        return GeminiProvider(settings.gemini_api_key, model)
    if name == "groq":
        return GroqProvider(settings.groq_api_key, model)
    raise ValueError(f"unknown PS_TRIAGEAI_LLM_PROVIDER_* value: {name!r}")


def build_gateway(settings: Settings) -> LLMGateway:
    """Wires the shared LLMGateway with the configured primary/fallback providers
    (`PS_TRIAGEAI_LLM_PROVIDER_PRIMARY`/`_FALLBACK`, default groq -> gemini). Constructing
    this never makes a network call; missing API keys fail closed on the first `.call()`."""
    primary = _build_provider(
        settings.llm_provider_primary,
        settings.llm_model_triage_primary or None,
        settings,
    )
    fallback = _build_provider(
        settings.llm_provider_fallback,
        settings.llm_model_triage_fallback or None,
        settings,
    )
    return LLMGateway(primary=primary, fallback=fallback)


__all__ = ["GeminiProvider", "GroqProvider", "LLMFailClosedError", "build_gateway"]
