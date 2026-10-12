"""Provider adapters wired to safepayai_common's LLM gateway INTERFACE (ADR-010).

Real Gemini (`google-genai`) and Groq (`openai` SDK pointed at Groq's OpenAI-compatible
endpoint) implementations, per `.claude/research/llm-integration-spec.md` sections 1-3 and
the build spec's section 1. Both providers:
- Request schema-constrained JSON output from the SDK.
- Re-validate the SDK's own output against the Pydantic schema on the CALLER's side
  (app/eval_validation.py) regardless of what the provider claims about constrained
  decoding -- compliant JSON is not the same as semantically-correct data (build spec
  section 1). This module only guarantees *parseable* JSON; schema/business validation
  happens one layer up.
- Allow exactly one same-provider retry for a timeout/5xx/schema-validation failure
  (including Groq's documented `json_validate_failed` 400, which research found occurs
  materially more often than Gemini's equivalent failure -- treated as expected
  transient, not a bug). NEVER retry on 429/402 -- go straight to fail-closed so the
  caller falls back to the next provider or a restrictive default.
- Raise `LLMFailClosedError` on any unrecoverable failure; never return a half-valid
  result. Callers (LLMGateway, then the routers) MUST fail closed, never crash into an
  undefined state (ADR-010).
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from safepayai_common.llm.gateway import LLMCallResult, LLMFailClosedError, LLMGateway

from app.settings import Settings

# HTTP/SDK status codes that are retry-eligible exactly once on the SAME provider
# (llm-integration-spec.md section 3): timeouts, 5xx, and schema-validation failures.
# 429 (rate limit) and 402 (quota/payment) are explicitly NOT retried here.
_NON_RETRYABLE_STATUS = {429, 402}


class GeminiProvider:
    """Primary provider: Google's `google-genai` unified SDK."""

    def __init__(self, api_key: str | None, model: str | None) -> None:
        self._api_key = api_key
        self._model = model

    async def call(
        self, prompt: str, json_schema: dict[str, Any], timeout_s: float
    ) -> LLMCallResult:
        if not self._api_key or not self._model:
            raise LLMFailClosedError(
                "gemini provider not configured (missing api key or model)"
            )

        last_error: Exception | None = None
        for attempt in range(2):  # primary attempt + 1 same-provider retry
            started = time.monotonic()
            try:
                output = await asyncio.wait_for(
                    self._call_once(prompt, json_schema), timeout=timeout_s
                )
                latency_ms = int((time.monotonic() - started) * 1000)
                return LLMCallResult(
                    valid=True,
                    output=output,
                    model_id=self._model,
                    latency_ms=latency_ms,
                )
            except _GeminiRetryable as exc:
                last_error = exc
                if attempt == 0:
                    continue
                break
            except _GeminiFatal as exc:
                raise LLMFailClosedError(f"gemini call failed: {exc}") from exc
            except TimeoutError as exc:
                last_error = exc
                if attempt == 0:
                    continue
                break
        raise LLMFailClosedError(f"gemini call failed after retry: {last_error}")

    async def _call_once(
        self, prompt: str, json_schema: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            from google import genai
            from google.genai import types
        except (
            ImportError
        ) as exc:  # pragma: no cover - dependency always installed in prod
            raise _GeminiFatal(f"google-genai not importable: {exc}") from exc

        assert self._model is not None  # guarded by call() before this method ever runs
        client = genai.Client(api_key=self._api_key)
        try:
            response = await client.aio.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=json_schema,
                    temperature=0.0,
                ),
            )
        except Exception as exc:
            status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
            if status in _NON_RETRYABLE_STATUS:
                raise _GeminiFatal(exc) from exc
            raise _GeminiRetryable(exc) from exc

        text = getattr(response, "text", None)
        if not text:
            raise _GeminiRetryable("empty response text")
        try:
            parsed: dict[str, Any] = json.loads(text)
            return parsed
        except json.JSONDecodeError as exc:
            # Schema-validation/parse failure -- retry-eligible per llm-integration-spec
            # section 3 ("schema-validation-failure" is a named retry-eligible case).
            raise _GeminiRetryable(f"non-JSON response: {exc}") from exc


class _GeminiRetryable(Exception):
    """Internal: a Gemini failure that is eligible for one same-provider retry."""


class _GeminiFatal(Exception):
    """Internal: a Gemini failure that must fail closed immediately (429/402/import)."""


class GroqProvider:
    """Fallback provider: `openai` SDK pointed at Groq's OpenAI-compatible endpoint."""

    _BASE_URL = "https://api.groq.com/openai/v1"

    def __init__(self, api_key: str | None, model: str | None) -> None:
        self._api_key = api_key
        self._model = model

    async def call(
        self, prompt: str, json_schema: dict[str, Any], timeout_s: float
    ) -> LLMCallResult:
        if not self._api_key or not self._model:
            raise LLMFailClosedError(
                "groq provider not configured (missing api key or model)"
            )

        last_error: Exception | None = None
        for attempt in range(2):  # primary attempt + 1 same-provider retry
            started = time.monotonic()
            try:
                output = await asyncio.wait_for(
                    self._call_once(prompt, json_schema), timeout=timeout_s
                )
                latency_ms = int((time.monotonic() - started) * 1000)
                return LLMCallResult(
                    valid=True,
                    output=output,
                    model_id=self._model,
                    latency_ms=latency_ms,
                )
            except _GroqRetryable as exc:
                last_error = exc
                if attempt == 0:
                    continue
                break
            except _GroqFatal as exc:
                raise LLMFailClosedError(f"groq call failed: {exc}") from exc
            except TimeoutError as exc:
                last_error = exc
                if attempt == 0:
                    continue
                break
        raise LLMFailClosedError(f"groq call failed after retry: {last_error}")

    async def _call_once(
        self, prompt: str, json_schema: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover
            raise _GroqFatal(f"openai sdk not importable: {exc}") from exc

        assert self._model is not None  # guarded by call() before this method ever runs
        client = AsyncOpenAI(api_key=self._api_key, base_url=self._BASE_URL)
        response_format: dict[str, Any] = {
            "type": "json_schema",
            "json_schema": {"name": "structured_output", "schema": json_schema},
        }
        try:
            # openai's stubs type response_format as a closed Union of TypedDicts and
            # don't accept a plain dict even though the runtime API does -- this is an
            # SDK typing limitation, not a real type error.
            response = await client.chat.completions.create(  # type: ignore[call-overload]
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                response_format=response_format,
            )
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            if status in _NON_RETRYABLE_STATUS:
                raise _GroqFatal(exc) from exc
            if status == 400:
                # Groq's documented json_validate_failed -- expected-often, retry-eligible
                # transient failure, not a bug (llm-integration-spec.md section 2/7).
                raise _GroqRetryable(exc) from exc
            if status is not None and status >= 500:
                raise _GroqRetryable(exc) from exc
            raise _GroqFatal(exc) from exc

        choice = response.choices[0] if response.choices else None
        content = choice.message.content if choice and choice.message else None
        if not content:
            raise _GroqRetryable("empty response content")
        try:
            parsed: dict[str, Any] = json.loads(content)
            return parsed
        except json.JSONDecodeError as exc:
            raise _GroqRetryable(f"non-JSON response: {exc}") from exc


class _GroqRetryable(Exception):
    """Internal: a Groq failure eligible for one same-provider retry."""


class _GroqFatal(Exception):
    """Internal: a Groq failure that must fail closed immediately (429/402/import)."""


def build_gateway(settings: Settings) -> LLMGateway:
    primary = GeminiProvider(settings.gemini_api_key, settings.llm_model_cart)
    fallback = GroqProvider(settings.groq_api_key, settings.llm_model_cart_fallback)
    return LLMGateway(primary=primary, fallback=fallback)


def build_fit_gateway(settings: Settings) -> LLMGateway:
    primary = GeminiProvider(settings.gemini_api_key, settings.llm_model_fit)
    fallback = GroqProvider(settings.groq_api_key, settings.llm_model_fit_fallback)
    return LLMGateway(primary=primary, fallback=fallback)


__all__ = [
    "GeminiProvider",
    "GroqProvider",
    "LLMFailClosedError",
    "build_fit_gateway",
    "build_gateway",
]
