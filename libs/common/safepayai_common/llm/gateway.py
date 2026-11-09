"""LLM gateway interface (ADR-010). Only shopping-agent and triage-ai import this.

Interface only — no provider SDK calls live here (that's each service's own adapter in Wave 5).
Every call must validate output against a JSON Schema and fail closed to the caller's restrictive
default (HUMAN_REVIEW / form-driven fallback) on any error, timeout, or schema failure. Raw model
output must never reach a money-moving code path — only validated enums/IDs may cross that boundary.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class LLMFailClosedError(Exception):
    """Raised by a provider adapter on timeout/429/schema-invalid output. Callers MUST catch this
    and fall back to their restrictive default; never retry into a money decision."""


@dataclass(frozen=True)
class LLMCallResult:
    valid: bool
    output: dict[str, Any] | None
    model_id: str
    latency_ms: int


class LLMProvider(Protocol):
    async def call(
        self, prompt: str, json_schema: dict[str, Any], timeout_s: float
    ) -> LLMCallResult: ...


class LLMGateway:
    """Provider-agnostic wrapper: primary then fallback, both validated, both logged (proposal_log /
    triage_log — see data-architecture.md §3), both subject to a per-case call cap enforced by the caller."""

    def __init__(self, primary: LLMProvider, fallback: LLMProvider | None = None):
        self._primary = primary
        self._fallback = fallback

    async def call(
        self, prompt: str, json_schema: dict[str, Any], timeout_s: float
    ) -> LLMCallResult:
        try:
            return await self._primary.call(prompt, json_schema, timeout_s)
        except LLMFailClosedError as exc:
            # Never the prompt or any key: only why the primary gave up (truncated). Without this
            # a primary that always fails is invisible; every answer just comes from the fallback.
            logger.warning("llm_primary_failed reason=%s", str(exc)[:300])
            if self._fallback is None:
                raise
            return await self._fallback.call(prompt, json_schema, timeout_s)
