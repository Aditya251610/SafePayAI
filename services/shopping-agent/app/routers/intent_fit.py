"""POST /intent-fit -- api.md section 5. Service-to-service only (svc:checkout).

Advisory-only: this endpoint never clears a hard block and never returns an HTTP error
for a model/provider failure -- it floors to `NEEDS_BUYER_CONFIRMATION`, `degraded=true`
(api.md section 5; build spec section 4 item 4, the tighten-only invariant, enforced in
code by `app.eval_validation.tighten_only`/`validate_intent_fit_output`, not just the
prompt).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.deps import ServicePrincipal, require_checkout_caller
from app.eval_validation import validate_intent_fit_output
from app.llm_providers import LLMFailClosedError, build_fit_gateway
from app.prompts import build_intent_fit_prompt
from app.schemas.propose import IntentFitRequest, IntentFitResponse
from app.settings import Settings, get_settings

router = APIRouter(tags=["intent-fit"])

FIT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["PASS", "NEEDS_BUYER_CONFIRMATION", "REJECT_WITH_REASON"],
        },
        "reason_code": {
            "type": "string",
            "enum": [
                "OK",
                "CATEGORY_MISMATCH",
                "QUANTITY_ODD",
                "RECIPIENT_MISMATCH",
                "UNCLEAR",
            ],
        },
        "reason": {"type": "string", "maxLength": 200},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["verdict", "reason_code", "reason", "confidence"],
    "additionalProperties": False,
}


def _degraded_response(reason: str, trace_id: str) -> IntentFitResponse:
    return IntentFitResponse(
        verdict="NEEDS_BUYER_CONFIRMATION",
        reason_code="UNCLEAR",
        reason=reason[:200],
        confidence=0.0,
        advisory=True,
        degraded=True,
        source="form",
        trace_id=trace_id,
    )


@router.post("/intent-fit", response_model=None)
async def intent_fit(
    body: IntentFitRequest,
    _principal: ServicePrincipal = Depends(require_checkout_caller),
    settings: Settings = Depends(get_settings),
) -> IntentFitResponse | JSONResponse:
    trace_id = str(uuid.uuid4())

    if not settings.llm_enabled:
        return _degraded_response(
            "AI assist paused (kill switch); defaulting to buyer confirmation.",
            trace_id,
        )

    cart_lines = [line.model_dump() for line in body.cart_lines]
    prompt = build_intent_fit_prompt(
        case_id=trace_id,
        cart_lines=cart_lines,
        buyer_intent_text=body.intent_text,
        untrusted_max_chars=settings.untrusted_max_chars,
    )
    gateway = build_fit_gateway(settings)
    try:
        result = await gateway.call(prompt, FIT_JSON_SCHEMA, settings.llm_timeout_fit_s)
    except LLMFailClosedError:
        return _degraded_response(
            "AI fit check unavailable; defaulting to buyer confirmation.", trace_id
        )

    outcome = validate_intent_fit_output(
        result.output or {},
        min_confidence=settings.fit_min_confidence,
    )

    return IntentFitResponse(
        verdict=outcome.verdict,  # type: ignore[arg-type]
        reason_code=outcome.reason_code,  # type: ignore[arg-type]
        reason=outcome.reason,
        confidence=outcome.confidence,
        advisory=True,
        degraded=outcome.floored or not outcome.schema_valid,
        source="live",
        trace_id=trace_id,
    )
