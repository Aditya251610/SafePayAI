"""Raw LLM output schemas (spec.md section 4). These are parsed with `model_validate`,
never trusted from provider "native JSON mode" alone (agent-and-mcp-design.md section 0;
llm-integration-spec.md section 7 #2: Groq's own structured-output mode is reported to
still fail ~10% of the time). The raw `LlmTriage`/`LlmDraft`/`LlmBrief` instance NEVER
leaves this service directly - app/service.py converts it into the public response shape
after applying every route/gate rule.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.triage import Category

FactField = Literal[
    "order_ref",
    "order_date",
    "promised_by",
    "state",
    "amount",
    "last_status",
    "last_status_ts",
    "delivered_ts",
]


class LlmTriage(BaseModel):
    """Raw /classify model output."""

    model_config = ConfigDict(extra="forbid")

    category: Category
    confidence: float = Field(ge=0, le=1)
    injection_suspected: bool
    evidence_quote: str | None = Field(default=None, max_length=200)


class LlmDraft(BaseModel):
    """Raw /draft model output - the regex gate (app/gate.py) runs on this AFTER parsing,
    before it is ever returned."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(max_length=80)
    body: str = Field(max_length=600)


class LlmFlag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_ids: list[str] = Field(default_factory=list, max_length=5)
    explanation: str = Field(max_length=160)


class LlmBrief(BaseModel):
    """Raw /brief model output. `fact_fields` is restricted to real server field names -
    the caller (app/service.py) builds `key_facts` from request data using these names,
    never from the model's own paraphrase of a value (llm-integration-spec.md section 4 #2)."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(max_length=500)
    fact_fields: list[FactField] = Field(default_factory=list, max_length=8)
    suggested_flags: list[LlmFlag] = Field(default_factory=list, max_length=3)
    open_questions: list[str] = Field(default_factory=list, max_length=4)


__all__ = ["FactField", "LlmBrief", "LlmDraft", "LlmFlag", "LlmTriage"]
