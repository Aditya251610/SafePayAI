"""POST /propose, GET /propose/{proposal_id} -- api.md sections 4, 6.

Live LLM wiring (build spec, this wave): intent mode grounds the model in a pre-
filtered catalog subset (app/catalog_filter.py), calls the real Gemini/Groq gateway
(app/llm_providers.py) via a prompt built in app/prompts.py, and re-validates every
output deterministically (app/eval_validation.py) before it can influence the
response -- the model is never the defence (spec.md section 4). Form mode and every
failure path (kill switch, breaker exhaustion, schema failure) route through the
deterministic matcher in app/form_fallback.py instead (spec.md section 7, conflict C6:
"form fallback first, NO_PROPOSAL only if form also cannot answer").

This endpoint never returns a price, total, merchant, or `proposal_hash` -- only
`{sku, qty}[]` + a display-only rationale (spec.md section 6). Downstream re-pricing
and hard checks at `checkout`/`mandate` remain authoritative regardless of `source`.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app_shopping_agent.catalog_filter import filter_catalog
from app_shopping_agent.clients import (
    CatalogUnavailableError,
    MandateNotFoundError,
    MandateUnavailableError,
    fetch_catalog_items,
    fetch_mandate_summary,
)
from app_shopping_agent.db import get_db
from app_shopping_agent.deps import (
    ServicePrincipal,
    mint_outbound_token,
    require_service_jwt,
)
from app_shopping_agent.eval_schemas import CART_PROPOSAL_JSON_SCHEMA
from app_shopping_agent.eval_validation import validate_cart_output
from app_shopping_agent.form_fallback import match_form_intent, match_free_text_fallback
from app_shopping_agent.llm_providers import LLMFailClosedError, build_gateway
from app_shopping_agent.persistence import (
    read_proposal_log,
    sha256_hex,
    write_cart_proposed_outbox,
    write_proposal_log,
)
from app_shopping_agent.prompts import build_cart_prompt
from app_shopping_agent.schemas.propose import (
    CartLineOut,
    ProposeRequest,
    ProposeResponse,
)
from app_shopping_agent.settings import Settings, get_settings

router = APIRouter(tags=["propose"])


def _display_title(sku: str, catalog_items: list[dict]) -> str | None:
    for item in catalog_items:
        if item["sku"] == sku:
            return item.get("title")
    return None


async def _load_mandate_and_catalog(
    settings: Settings, mandate_id: str
) -> tuple[dict, list[dict]]:
    # Each downstream call needs its own correctly-audienced service token (aud=
    # "mandate"/"catalog"), minted here via mint_outbound_token - NOT the inbound
    # gateway token (aud="agent"), which every downstream service's own audience
    # check would reject. Was previously forwarding the inbound token as a
    # documented, deferred gap (see app/clients.py's old module docstring); fixed
    # by minting properly, same pattern checkout already uses.
    try:
        mandate_summary = await fetch_mandate_summary(
            base_url=settings.mandate_base_url,
            mandate_id=mandate_id,
            bearer_token=mint_outbound_token(settings, "mandate"),
        )
    except MandateNotFoundError as exc:
        raise _ProposeError(404, "MANDATE_NOT_FOUND", str(exc)) from exc
    except MandateUnavailableError as exc:
        raise _ProposeError(503, "MANDATE_UNAVAILABLE", str(exc)) from exc

    try:
        catalog_items = await fetch_catalog_items(
            base_url=settings.catalog_base_url,
            bearer_token=mint_outbound_token(settings, "catalog"),
        )
    except CatalogUnavailableError as exc:
        raise _ProposeError(503, "CATALOG_UNAVAILABLE", str(exc)) from exc

    return mandate_summary, catalog_items


class _ProposeError(Exception):
    def __init__(self, status_code: int, code: str, detail: str) -> None:
        self.status_code = status_code
        self.code = code
        self.detail = detail
        super().__init__(detail)


def _error_response(exc: _ProposeError, trace_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "detail": exc.detail, "request_id": trace_id},
    )


async def _persist(
    session: AsyncSession,
    *,
    trace_id: uuid.UUID,
    mandate_id: uuid.UUID,
    prompt_version: str,
    provider: str | None,
    model: str | None,
    source: str,
    input_text: str,
    output_json: dict | None,
    validation_result: str | None,
    injection_suspected: bool,
    latency_ms: int | None,
    attempts: int,
    status: str,
) -> uuid.UUID:
    input_sha256 = sha256_hex(input_text)
    output_sha256 = sha256_hex(str(output_json)) if output_json is not None else None
    proposal_id = await write_proposal_log(
        session,
        trace_id=trace_id,
        mandate_id=mandate_id,
        kind="cart",
        prompt_version=prompt_version,
        provider=provider,
        model=model,
        source=source,
        input_sha256=input_sha256,
        output_sha256=output_sha256,
        output_json=output_json,
        validation_result=validation_result,
        injection_suspected=injection_suspected,
        latency_ms=latency_ms,
        attempts=attempts,
    )
    if status != "NO_PROPOSAL":
        await write_cart_proposed_outbox(
            session,
            proposal_id=proposal_id,
            mandate_id=mandate_id,
            trace_id=trace_id,
            prompt_version=prompt_version,
            provider=provider,
            model=model,
            source=source,
            input_sha256=input_sha256,
            output_sha256=output_sha256,
            validation_result=validation_result,
            injection_suspected=injection_suspected,
            latency_ms=latency_ms,
        )
    await session.commit()
    return proposal_id


@router.post("/propose", response_model=None)
async def propose(
    body: ProposeRequest,
    _principal: ServicePrincipal = Depends(require_service_jwt),
    settings: Settings = Depends(get_settings),
    db: AsyncSession = Depends(get_db),
) -> ProposeResponse | JSONResponse:
    trace_id = uuid.uuid4()

    try:
        mandate_summary, catalog_items = await _load_mandate_and_catalog(
            settings, body.mandate_id
        )
    except _ProposeError as exc:
        return _error_response(exc, str(trace_id))

    allowed_merchant_ids = set(mandate_summary.get("allowed_merchant_ids", []))
    sku_to_merchant = {item["sku"]: item["merchant_id"] for item in catalog_items}
    catalog_skus = set(sku_to_merchant)

    lines: list[CartLineOut] = []
    status: Literal["OK", "NO_MATCH", "NO_PROPOSAL", "AI_PAUSED"] = "NO_PROPOSAL"
    source: Literal["live", "cached", "form"] = "form"
    rationale: str | None = None
    confidence: float | None = None
    no_match_reason: str | None = None
    model_id: str | None = None
    latency_ms: int | None = None
    provider: str | None = None
    validation_result: str | None = None
    injection_suspected = False
    input_text_for_hash = ""

    if body.mode == "form":
        form = body.form
        if form is None:
            missing_form_error = _ProposeError(
                422, "INVALID_REQUEST", "form mode requires form fields"
            )
            return _error_response(missing_form_error, str(trace_id))
        input_text_for_hash = f"form:{form.category}:{form.max_budget_minor}:{form.quantity}:{form.merchant_id}"
        matches = match_form_intent(
            catalog_items,
            category=form.category,
            max_budget_minor=min(
                form.max_budget_minor,
                mandate_summary.get("max_total_minor", form.max_budget_minor),
            ),
            quantity=form.quantity,
            allowed_merchant_ids=allowed_merchant_ids,
            merchant_id=form.merchant_id,
            keywords=form.keywords,
        )
        if matches:
            status = "OK"
            lines = [
                CartLineOut(
                    sku=m.sku, quantity=m.quantity, display_title=m.display_title
                )
                for m in matches
            ]
            rationale = (
                "Matched deterministically from your category, budget, and quantity."
            )
        else:
            status = "NO_MATCH"
            no_match_reason = "No catalog item fits the given category/budget/quantity."
        validation_result = status

    else:  # mode == "intent"
        intent_text = body.intent_text or ""
        input_text_for_hash = intent_text
        if not settings.llm_enabled:
            status = "AI_PAUSED"
            fallback = match_free_text_fallback(
                catalog_items,
                intent_text=intent_text,
                allowed_merchant_ids=allowed_merchant_ids,
            )
            if fallback:
                lines = [
                    CartLineOut(
                        sku=m.sku, quantity=m.quantity, display_title=m.display_title
                    )
                    for m in fallback
                ]
                rationale = "AI assist paused (free-tier limit) - using form mode."
            else:
                no_match_reason = "AI assist paused; no deterministic match either."
            validation_result = status
        else:
            catalog_subset = filter_catalog(
                catalog_items,
                intent_text=intent_text,
                allowed_merchant_ids=allowed_merchant_ids,
            )
            prompt = build_cart_prompt(
                case_id=str(trace_id),
                mandate_summary=mandate_summary,
                catalog_subset=catalog_subset,
                buyer_intent_text=intent_text,
                intent_max_chars=settings.intent_max_chars,
                untrusted_max_chars=settings.untrusted_max_chars,
            )
            gateway = build_gateway(settings)
            try:
                result = await gateway.call(
                    prompt, CART_PROPOSAL_JSON_SCHEMA, settings.llm_timeout_cart_s
                )
                model_id = result.model_id
                latency_ms = result.latency_ms
                provider = settings.llm_provider
                outcome = validate_cart_output(
                    result.output or {},
                    catalog_skus=catalog_skus,
                    sku_to_merchant=sku_to_merchant,
                    allowed_merchant_ids=allowed_merchant_ids,
                )
                validation_result = outcome.status
                injection_suspected = outcome.injection_suspected

                if outcome.status == "OK":
                    status = "OK"
                    source = "live"
                    lines = [
                        CartLineOut(
                            sku=accepted["sku"],
                            quantity=accepted["quantity"],
                            display_title=_display_title(
                                accepted["sku"], catalog_items
                            ),
                        )
                        for accepted in outcome.accepted_lines
                    ]
                    rationale = (result.output or {}).get("rationale")
                    confidence = (result.output or {}).get("confidence")
                elif outcome.status == "NO_MATCH":
                    status = "NO_MATCH"
                    source = "live"
                    no_match_reason = outcome.detail
                else:
                    # SCHEMA_INVALID or HARD_GATE_VIOLATION: never partially trust the
                    # model output -- fall back to the deterministic matcher instead
                    # (conflict C6: form fallback first, NO_PROPOSAL only if that fails
                    # too).
                    fallback = match_free_text_fallback(
                        catalog_items,
                        intent_text=intent_text,
                        allowed_merchant_ids=allowed_merchant_ids,
                    )
                    if fallback:
                        status = "OK"
                        lines = [
                            CartLineOut(
                                sku=m.sku,
                                quantity=m.quantity,
                                display_title=m.display_title,
                            )
                            for m in fallback
                        ]
                        rationale = "Matched deterministically after the AI proposal failed validation."
                    else:
                        status = "NO_PROPOSAL"
            except LLMFailClosedError as exc:
                validation_result = f"LLM_FAIL_CLOSED: {exc}"
                fallback = match_free_text_fallback(
                    catalog_items,
                    intent_text=intent_text,
                    allowed_merchant_ids=allowed_merchant_ids,
                )
                if fallback:
                    status = "OK"
                    lines = [
                        CartLineOut(
                            sku=m.sku,
                            quantity=m.quantity,
                            display_title=m.display_title,
                        )
                        for m in fallback
                    ]
                    rationale = (
                        "AI assist unavailable - matched deterministically instead."
                    )
                else:
                    status = "NO_PROPOSAL"

    # Stored distinct from the raw provider output: this is the FINAL, validated,
    # response-shaped payload (so GET /propose/{id} can re-serialize it verbatim without
    # re-running validation, per api.md section 6 - "no re-validation, no new model call").
    response_payload: dict[str, Any] = {
        "status": status,
        "lines": [line.model_dump() for line in lines],
        "rationale": rationale,
        "confidence": confidence,
        "no_match_reason": no_match_reason,
    }

    proposal_id = trace_id
    try:
        proposal_id = await _persist(
            db,
            trace_id=trace_id,
            mandate_id=uuid.UUID(body.mandate_id),
            prompt_version=settings.prompt_version_cart,
            provider=provider,
            model=model_id,
            source=source,
            input_text=input_text_for_hash,
            output_json=response_payload,
            validation_result=validation_result,
            injection_suspected=injection_suspected,
            latency_ms=latency_ms,
            attempts=1,
            status=status,
        )
    except Exception:  # noqa: BLE001 - persistence must never hide the computed result
        await db.rollback()

    return ProposeResponse(
        proposal_id=str(proposal_id),
        status=status,
        source=source,
        lines=lines,
        rationale=rationale,
        confidence=confidence,
        no_match_reason=no_match_reason,
        model=model_id,
        latency_ms=latency_ms,
        badge=None,
        recorded_model=None,
        trace_id=str(trace_id),
    )


@router.get("/propose/{proposal_id}", response_model=None)
async def get_propose(
    proposal_id: str,
    _principal: ServicePrincipal = Depends(require_service_jwt),
    db: AsyncSession = Depends(get_db),
) -> ProposeResponse | JSONResponse:
    trace_id = str(uuid.uuid4())
    try:
        row = await read_proposal_log(db, uuid.UUID(proposal_id))
    except ValueError:
        row = None
    if row is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": "PROPOSAL_NOT_FOUND",
                "detail": "no such proposal",
                "request_id": trace_id,
            },
        )
    output_json = row.get("output_json") or {}
    lines = [CartLineOut(**line) for line in output_json.get("lines", [])]
    return ProposeResponse(
        proposal_id=str(row["id"]),
        status=output_json.get("status", "OK"),
        source=row["source"],
        lines=lines,
        rationale=output_json.get("rationale"),
        confidence=output_json.get("confidence"),
        no_match_reason=output_json.get("no_match_reason"),
        model=row.get("model"),
        latency_ms=row.get("latency_ms"),
        badge=None,
        recorded_model=None,
        trace_id=str(row["trace_id"]),
    )
