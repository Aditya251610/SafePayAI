"""Orchestrates /classify, /draft, /brief (spec.md sections 5-8). AI never decides money:
every path here ends in a validated enum, a regex-gated string, or a read-only summary built
from server facts. Fails closed to HUMAN_REVIEW / a static template on ANY error - bad JSON,
timeout, low confidence, injection, kill switch - never raises out of this module for a
model/provider failure (those are not transport errors, per api.md section 0).
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any

from pydantic import ValidationError
from safepayai_common.llm.gateway import LLMFailClosedError, LLMGateway

from app import consistency, templates, untrusted
from app.gate import check_gate
from app.llm_io import LlmBrief, LlmDraft, LlmTriage
from app.prompts import build_brief_prompt, build_classify_prompt, build_draft_prompt
from app.schemas.triage import (
    BriefRequest,
    BriefResponse,
    ClassifyRequest,
    ClassifyResponse,
    DraftRequest,
    DraftResponse,
    InconsistencyFlag,
    KeyFact,
    Provenance,
)
from app.settings import Settings

# category -> rule-flag codes that, if present at WARN, contradict that category and force
# HUMAN_REVIEW regardless of the model's own confidence (spec.md section 5 step 7).
CONTRADICTING_FLAGS: dict[str, set[str]] = {
    "LOST": {"CLAIM_NOT_RECEIVED_BUT_DELIVERED"},
    "LATE": {"CLAIM_LATE_BUT_ON_TIME"},
    "DAMAGED": {"CLAIM_DAMAGED_BUT_NOT_DELIVERED"},
    "WRONG_ITEM": {"CLAIM_WRONG_ITEM_BUT_NOT_DELIVERED"},
    "NOT_AS_DESCRIBED": {"CLAIM_WRONG_ITEM_BUT_NOT_DELIVERED"},
}


def input_hash(*parts: str) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def classify_input_hash(body: ClassifyRequest, settings: Settings) -> str:
    """Single source of truth for the idempotency key's input hash - used both by the
    router's pre-call lookup and internally by `classify()`, so the two can never diverge."""
    sanitized_text, _ = untrusted.sanitize_text(
        body.buyer_text, settings.max_text_chars
    )
    carrier_raw = " | ".join(e.note for e in body.timeline if e.note)
    carrier_sanitized, _ = untrusted.sanitize_text(carrier_raw, settings.max_text_chars)
    return input_hash(
        str(body.case_id),
        "classify",
        settings.prompt_version,
        sanitized_text,
        carrier_sanitized,
    )


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _fail_closed_classify(
    *,
    triage_id: uuid.UUID,
    reasons: list[str],
    started: float,
    settings: Settings,
    rule_flags: list[dict[str, Any]] | None = None,
    model: str | None = None,
) -> ClassifyResponse:
    return ClassifyResponse(
        triage_id=triage_id,
        category="OTHER",
        confidence=0.0,
        route="HUMAN_REVIEW",
        reasons=reasons,
        timeline_flags=[InconsistencyFlag(**f) for f in (rule_flags or [])],
        provenance=Provenance(
            source="rules",
            model=model,
            prompt_version=settings.prompt_version,
            cached_at=None,
            latency_ms=_elapsed_ms(started),
        ),
    )


async def classify(
    body: ClassifyRequest, settings: Settings, gateway: LLMGateway
) -> tuple[ClassifyResponse, dict[str, Any]]:
    """Returns (response, log_fields). `log_fields` feeds repo.insert_triage_log - it never
    carries raw buyer/carrier text, only hashes and codes (spec.md section 10)."""
    started = time.monotonic()
    triage_id = uuid.uuid4()

    sanitized_text, truncated = untrusted.sanitize_text(
        body.buyer_text, settings.max_text_chars
    )
    carrier_raw = " | ".join(e.note for e in body.timeline if e.note)
    carrier_sanitized, carrier_truncated = untrusted.sanitize_text(
        carrier_raw, settings.max_text_chars
    )
    truncated = truncated or carrier_truncated

    in_hash = classify_input_hash(body, settings)

    def log(
        response: ClassifyResponse, source: str, model: str | None
    ) -> dict[str, Any]:
        return {
            "triage_id": str(response.triage_id),
            "case_id": str(body.case_id),
            "trace_id": body.trace_id,
            "task": "classify",
            "prompt_version": settings.prompt_version,
            "model": model,
            "source": source,
            "input_sha256": in_hash,
            "output_sha256": input_hash(response.model_dump_json()),
            "category": response.category,
            "confidence": response.confidence,
            "route": response.route,
            "reasons": json.dumps(response.reasons),
            "flags": json.dumps([f.model_dump() for f in response.timeline_flags]),
            "gate_hits": json.dumps([]),
            "tokens_in": None,
            "tokens_out": None,
            "latency_ms": response.provenance.latency_ms,
            "status": response.route,
            "truncated": truncated,
        }

    if body.origin == "detector":
        # Detector-originated cases skip text classification entirely (spec.md section 5
        # step 1); resolution already knows the detector kind and calls /draft + /brief only.
        response = _fail_closed_classify(
            triage_id=triage_id, reasons=["OK"], started=started, settings=settings
        )
        return response, log(response, "rules", None)

    if not sanitized_text.strip():
        response = _fail_closed_classify(
            triage_id=triage_id,
            reasons=["EMPTY_INPUT"],
            started=started,
            settings=settings,
        )
        return response, log(response, "rules", None)

    rule_flags = consistency.compute_timeline_flags(
        buyer_text=sanitized_text,
        timeline=body.timeline,
        promised_by=body.order.promised_by,
        demo_now=body.order.demo_now,
        stale_window_hours=settings.stale_window_hours or 48,
    )

    if not settings.llm_enabled:
        response = _fail_closed_classify(
            triage_id=triage_id,
            reasons=["KILL_SWITCH"],
            started=started,
            settings=settings,
            rule_flags=rule_flags,
        )
        return response, log(response, "rules", None)

    nonce = untrusted.make_nonce()
    prompt, json_schema = build_classify_prompt(
        order=body.order,
        buyer_text=sanitized_text,
        carrier_notes=carrier_sanitized,
        case_id=str(body.case_id),
        nonce=nonce,
    )

    try:
        result = await gateway.call(prompt, json_schema, settings.timeout_classify_s)
    except LLMFailClosedError:
        response = _fail_closed_classify(
            triage_id=triage_id,
            reasons=["LLM_ERROR"],
            started=started,
            settings=settings,
            rule_flags=rule_flags,
        )
        return response, log(response, "rules", None)

    if not result.valid or result.output is None:
        response = _fail_closed_classify(
            triage_id=triage_id,
            reasons=["SCHEMA_FAIL"],
            started=started,
            settings=settings,
            rule_flags=rule_flags,
            model=result.model_id,
        )
        return response, log(response, "rules", result.model_id)

    try:
        llm_out = LlmTriage.model_validate(result.output)
    except ValidationError:
        response = _fail_closed_classify(
            triage_id=triage_id,
            reasons=["SCHEMA_FAIL"],
            started=started,
            settings=settings,
            rule_flags=rule_flags,
            model=result.model_id,
        )
        return response, log(response, "rules", result.model_id)

    reasons: list[str] = []
    route: str = "PROCEED"

    if llm_out.injection_suspected:
        reasons.append("INJECTION_SUSPECTED")
        route = "HUMAN_REVIEW"

    if llm_out.evidence_quote:
        haystack = f"{sanitized_text}\n{carrier_sanitized}".lower()
        if llm_out.evidence_quote.lower() not in haystack:
            reasons.append("EVIDENCE_NOT_IN_INPUT")
            route = "HUMAN_REVIEW"

    if llm_out.confidence < settings.min_confidence:
        reasons.append("LOW_CONFIDENCE")
        route = "HUMAN_REVIEW"

    contradicting_codes = CONTRADICTING_FLAGS.get(llm_out.category, set())
    if any(
        f["code"] in contradicting_codes and f["severity"] == "WARN" for f in rule_flags
    ):
        reasons.append("TIMELINE_CONFLICT")
        route = "HUMAN_REVIEW"

    if llm_out.category == "OTHER":
        # OTHER has no automated path; resolution treats OTHER as review (spec.md section 5).
        route = "HUMAN_REVIEW"

    if not reasons:
        reasons = ["OK"]

    response = ClassifyResponse(
        triage_id=triage_id,
        category=llm_out.category,
        confidence=llm_out.confidence,
        route=route,  # type: ignore[arg-type]
        reasons=reasons,
        timeline_flags=[InconsistencyFlag(**f) for f in rule_flags],
        provenance=Provenance(
            source="live",
            model=result.model_id,
            prompt_version=settings.prompt_version,
            cached_at=None,
            latency_ms=_elapsed_ms(started),
        ),
    )
    return response, log(response, "live", result.model_id)


async def draft(
    body: DraftRequest, settings: Settings, gateway: LLMGateway
) -> tuple[DraftResponse, dict[str, Any]]:
    started = time.monotonic()
    triage_id = uuid.uuid4()
    in_hash = input_hash(
        str(body.case_id), "draft", settings.prompt_version, body.category, body.outcome
    )

    def log(
        response: DraftResponse, source: str, model: str | None, gate_hits: list[str]
    ) -> dict[str, Any]:
        return {
            "triage_id": str(response.triage_id),
            "case_id": str(body.case_id),
            "trace_id": body.trace_id,
            "task": "draft",
            "prompt_version": settings.prompt_version,
            "model": model,
            "source": source,
            "input_sha256": in_hash,
            "output_sha256": input_hash(response.model_dump_json()),
            "category": body.category,
            "confidence": None,
            "route": None,
            "reasons": json.dumps([]),
            "flags": json.dumps([]),
            "gate_hits": json.dumps(gate_hits),
            "tokens_in": None,
            "tokens_out": None,
            "latency_ms": response.provenance.latency_ms,
            "status": response.gate,
            "truncated": False,
        }

    def fallback(
        gate_hits: list[str], model: str | None
    ) -> tuple[DraftResponse, dict[str, Any]]:
        subject, body_text, placeholders = templates.static_draft(
            body.category, body.outcome, body.order_ref
        )
        response = DraftResponse(
            triage_id=triage_id,
            subject=subject,
            body=body_text,
            placeholders_used=placeholders,  # type: ignore[arg-type]
            gate="REJECTED_USED_TEMPLATE",
            gate_hits=gate_hits,
            provenance=Provenance(
                source="template",
                model=model,
                prompt_version=settings.prompt_version,
                cached_at=None,
                latency_ms=_elapsed_ms(started),
            ),
        )
        return response, log(response, "template", model, gate_hits)

    if not settings.llm_enabled:
        return fallback([], None)

    prompt, json_schema = build_draft_prompt(
        category=body.category, outcome=body.outcome, order_ref=body.order_ref
    )

    try:
        result = await gateway.call(prompt, json_schema, settings.timeout_draft_s)
    except LLMFailClosedError:
        return fallback(["LLM_ERROR"], None)

    if not result.valid or result.output is None:
        return fallback(["SCHEMA_FAIL"], result.model_id)

    try:
        llm_out = LlmDraft.model_validate(result.output)
    except ValidationError:
        return fallback(["SCHEMA_FAIL"], result.model_id)

    # The regex gate - NOT the prompt instruction - is the real security boundary here.
    # Never retry the LLM on a gate failure (llm-integration-spec.md section 5): fall
    # straight back to the free, instant, reviewed static template.
    gate_hits = check_gate(f"{llm_out.subject}\n{llm_out.body}")
    if gate_hits:
        return fallback(gate_hits, result.model_id)

    combined = f"{llm_out.subject}\n{llm_out.body}"
    placeholders_used = [
        p
        for p in ("{amount}", "{order_ref}", "{date}", "{buyer_name}")
        if p in combined
    ]

    response = DraftResponse(
        triage_id=triage_id,
        subject=llm_out.subject,
        body=llm_out.body,
        placeholders_used=placeholders_used,  # type: ignore[arg-type]
        gate="PASSED",
        gate_hits=[],
        provenance=Provenance(
            source="live",
            model=result.model_id,
            prompt_version=settings.prompt_version,
            cached_at=None,
            latency_ms=_elapsed_ms(started),
        ),
    )
    return response, log(response, "live", result.model_id, [])


_FACT_LABELS: dict[str, str] = {
    "order_ref": "order_ref",
    "order_date": "order_date",
    "promised_by": "promised_by",
    "state": "state",
    "amount": "amount_minor",
    "last_status": "timeline[-1].status",
    "last_status_ts": "timeline[-1].ts",
    "delivered_ts": "timeline[DELIVERED].ts",
}


def _build_key_facts(fact_fields: list[str], body: BriefRequest) -> list[KeyFact]:
    """Builds `key_facts` entries FROM REQUEST DATA ONLY, keyed by a real server field name
    the model may have suggested surfacing - never from the model's own paraphrase of a
    value (llm-integration-spec.md section 4 #2)."""
    facts: list[KeyFact] = []
    order = body.order
    for field in fact_fields:
        if field == "order_ref":
            facts.append(
                KeyFact(
                    field=field, value=order.order_ref, source_field="order.order_ref"
                )
            )
        elif field == "order_date":
            facts.append(
                KeyFact(
                    field=field,
                    value=order.order_date.isoformat(),
                    source_field="order.order_date",
                )
            )
        elif field == "promised_by" and order.promised_by:
            facts.append(
                KeyFact(
                    field=field,
                    value=order.promised_by.isoformat(),
                    source_field="order.promised_by",
                )
            )
        elif field == "state":
            facts.append(
                KeyFact(field=field, value=order.state, source_field="order.state")
            )
        elif field == "amount" and order.amount_minor is not None:
            facts.append(
                KeyFact(
                    field=field,
                    value=f"{order.amount_minor / 100:.2f} {order.currency or ''}".strip(),
                    source_field="order.amount_minor",
                )
            )
        elif field in ("last_status", "last_status_ts") and body.timeline:
            last_event = max(body.timeline, key=lambda e: e.ts)
            if field == "last_status":
                facts.append(
                    KeyFact(
                        field=field,
                        value=last_event.status,
                        source_field="timeline[-1].status",
                    )
                )
            else:
                facts.append(
                    KeyFact(
                        field=field,
                        value=last_event.ts.isoformat(),
                        source_field="timeline[-1].ts",
                    )
                )
        elif field == "delivered_ts":
            delivered = [e for e in body.timeline if e.status == "DELIVERED"]
            if delivered:
                ts = min(e.ts for e in delivered)
                facts.append(
                    KeyFact(
                        field=field,
                        value=ts.isoformat(),
                        source_field="timeline[DELIVERED].ts",
                    )
                )
    return facts


async def brief(
    body: BriefRequest, settings: Settings, gateway: LLMGateway
) -> tuple[BriefResponse, dict[str, Any]]:
    started = time.monotonic()
    triage_id = uuid.uuid4()

    sanitized_text, truncated = untrusted.sanitize_text(
        body.buyer_text, settings.max_text_chars
    )

    rule_flags = consistency.compute_timeline_flags(
        buyer_text=sanitized_text,
        timeline=body.timeline,
        promised_by=body.order.promised_by,
        demo_now=body.order.demo_now,
        stale_window_hours=settings.stale_window_hours or 48,
    )

    category = body.triage.category if body.triage else None
    in_hash = input_hash(
        str(body.case_id), "brief", settings.prompt_version, sanitized_text
    )

    def log(response: BriefResponse, source: str, model: str | None) -> dict[str, Any]:
        return {
            "triage_id": str(response.triage_id),
            "case_id": str(body.case_id),
            "trace_id": body.trace_id,
            "task": "brief",
            "prompt_version": settings.prompt_version,
            "model": model,
            "source": source,
            "input_sha256": in_hash,
            "output_sha256": input_hash(response.model_dump_json()),
            "category": category,
            "confidence": None,
            "route": None,
            "reasons": json.dumps([]),
            "flags": json.dumps([f.model_dump() for f in response.inconsistency_flags]),
            "gate_hits": json.dumps([]),
            "tokens_in": None,
            "tokens_out": None,
            "latency_ms": response.provenance.latency_ms,
            "status": "OK",
            "truncated": truncated,
        }

    def fallback(model: str | None) -> tuple[BriefResponse, dict[str, Any]]:
        response = BriefResponse(
            triage_id=triage_id,
            summary=templates.static_brief_summary(
                category=category, state=body.order.state
            ),
            key_facts=_build_key_facts(
                ["order_ref", "order_date", "state", "amount"], body
            ),
            inconsistency_flags=[InconsistencyFlag(**f) for f in rule_flags],
            open_questions=[],
            provenance=Provenance(
                source="template",
                model=model,
                prompt_version=settings.prompt_version,
                cached_at=None,
                latency_ms=_elapsed_ms(started),
            ),
        )
        return response, log(response, "template", model)

    if not settings.llm_enabled:
        return fallback(None)

    nonce = untrusted.make_nonce()
    prompt, json_schema = build_brief_prompt(
        order=body.order,
        buyer_text=sanitized_text,
        policy_decision=body.policy_decision,
        case_id=str(body.case_id),
        nonce=nonce,
    )

    try:
        result = await gateway.call(prompt, json_schema, settings.timeout_brief_s)
    except LLMFailClosedError:
        return fallback(None)

    if not result.valid or result.output is None:
        return fallback(result.model_id)

    try:
        llm_out = LlmBrief.model_validate(result.output)
    except ValidationError:
        return fallback(result.model_id)

    summary_gate_hits = check_gate(llm_out.summary) + [
        hit for q in llm_out.open_questions for hit in check_gate(q)
    ]
    if summary_gate_hits:
        return fallback(result.model_id)

    model_flags: list[InconsistencyFlag] = []
    valid_event_ids = {e.event_id for e in body.timeline}
    for flag in llm_out.suggested_flags:
        if not flag.event_ids or not set(flag.event_ids).issubset(valid_event_ids):
            continue
        if check_gate(flag.explanation):
            continue
        # The model can never raise WARN - only rules can (spec.md section 8.1 step 3).
        model_flags.append(
            InconsistencyFlag(
                code="MODEL_SUGGESTED",
                severity="INFO",
                origin="model",
                event_ids=flag.event_ids,
                explanation=flag.explanation,
            )
        )

    response = BriefResponse(
        triage_id=triage_id,
        summary=llm_out.summary,
        key_facts=_build_key_facts(list(llm_out.fact_fields), body),
        inconsistency_flags=[InconsistencyFlag(**f) for f in rule_flags] + model_flags,
        open_questions=llm_out.open_questions,
        provenance=Provenance(
            source="live",
            model=result.model_id,
            prompt_version=settings.prompt_version,
            cached_at=None,
            latency_ms=_elapsed_ms(started),
        ),
    )
    return response, log(response, "live", result.model_id)


__all__ = ["brief", "classify", "classify_input_hash", "draft", "input_hash"]
