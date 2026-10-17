"""Deterministic, service-side validation of a (schema-valid) CartProposal, per
spec.md section 3 steps 2-4. This is the layer that actually enforces safety -- the
model is never the defence (spec.md section 4). Pure functions, no I/O, fully
unit-testable and reused by both the eval harness and (in a later wave) the live
`/propose` endpoint.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pydantic import ValidationError

from app_shopping_agent.eval_schemas import CartProposal, IntentFit

# Strictness order (spec.md section 5): PASS < NEEDS_BUYER_CONFIRMATION < REJECT_WITH_REASON.
_VERDICT_RANK = {
    "PASS": 0,
    "NEEDS_BUYER_CONFIRMATION": 1,
    "REJECT_WITH_REASON": 2,
}

INJECTION_PATTERNS = [
    re.compile(r"https?://", re.IGNORECASE),
    re.compile(
        r"\bignore\b.{0,30}\b(rules|instructions|system prompt)\b", re.IGNORECASE
    ),
    re.compile(
        r"\bcall\b.{0,20}\b(refund_capture|refund_order|propose_cart)\b", re.IGNORECASE
    ),
    re.compile(r"\bsystem\s*:", re.IGNORECASE),
    re.compile(r"</?untrusted_", re.IGNORECASE),
]


@dataclass
class ValidationOutcome:
    schema_valid: bool
    hard_gate_violation: (
        bool  # hallucinated SKU, non-allowlisted merchant accepted, etc.
    )
    injection_suspected: bool
    status: str  # OK, NO_MATCH, SCHEMA_INVALID, HARD_GATE_VIOLATION
    detail: str
    accepted_lines: list[dict] = field(default_factory=list)


def _detect_injection(text: str | None) -> bool:
    if not text:
        return False
    return any(p.search(text) for p in INJECTION_PATTERNS)


def validate_cart_output(
    raw: dict,
    *,
    catalog_skus: set[str],
    sku_to_merchant: dict[str, str],
    allowed_merchant_ids: set[str],
    max_qty_per_line: int = 5,
) -> ValidationOutcome:
    """spec.md section 3's deterministic validation order; first failure discards
    the model output entirely (fail closed, never partially trust it)."""
    # Step 1: parse + schema (extra fields like price/total/merchant fail here).
    try:
        proposal = CartProposal.model_validate(raw)
    except ValidationError as exc:
        return ValidationOutcome(
            schema_valid=False,
            hard_gate_violation=False,
            injection_suspected=_detect_injection(str(raw)),
            status="SCHEMA_INVALID",
            detail=str(exc)[:500],
        )

    injection_suspected = _detect_injection(proposal.rationale) or _detect_injection(
        proposal.no_match_reason
    )

    if not proposal.items:
        return ValidationOutcome(
            schema_valid=True,
            hard_gate_violation=False,
            injection_suspected=injection_suspected,
            status="NO_MATCH",
            detail=proposal.no_match_reason or "empty items",
        )

    # Step 2: every sku must exist in the supplied catalog snapshot (no invented SKUs).
    hallucinated = [line.sku for line in proposal.items if line.sku not in catalog_skus]
    if hallucinated:
        return ValidationOutcome(
            schema_valid=True,
            hard_gate_violation=True,
            injection_suspected=injection_suspected,
            status="HARD_GATE_VIOLATION",
            detail=f"hallucinated SKU(s): {hallucinated}",
        )

    # Step 3: merchant allowlist + qty caps; duplicate SKU lines merged.
    merged: dict[str, int] = {}
    for line in proposal.items:
        merged[line.sku] = merged.get(line.sku, 0) + line.quantity

    not_allowed = [
        sku for sku in merged if sku_to_merchant.get(sku) not in allowed_merchant_ids
    ]
    if not_allowed:
        return ValidationOutcome(
            schema_valid=True,
            hard_gate_violation=True,
            injection_suspected=injection_suspected,
            status="HARD_GATE_VIOLATION",
            detail=f"non-allowlisted merchant for SKU(s): {not_allowed}",
        )

    over_qty = {sku: qty for sku, qty in merged.items() if qty > max_qty_per_line}
    accepted_lines = [
        {"sku": sku, "quantity": min(qty, max_qty_per_line)}
        for sku, qty in merged.items()
    ]

    return ValidationOutcome(
        schema_valid=True,
        hard_gate_violation=False,
        injection_suspected=injection_suspected,
        status="OK",
        detail="capped qty: " + str(over_qty) if over_qty else "ok",
        accepted_lines=accepted_lines,
    )


@dataclass
class IntentFitOutcome:
    schema_valid: bool
    verdict: str
    reason_code: str
    reason: str
    confidence: float
    floored: bool  # true if a deterministic floor overrode the model's raw verdict
    detail: str


def validate_intent_fit_output(
    raw: dict,
    *,
    min_confidence: float,
    injection_suspected: bool = False,
) -> IntentFitOutcome:
    """build spec section 4 step 4 (tighten-only invariant), enforced in code, not just
    the prompt: the verdict this function returns is NEVER less restrictive than the
    floor implied by low confidence, injection suspicion, or schema failure. Any failure
    here (schema-invalid output) floors at NEEDS_BUYER_CONFIRMATION, never PASS."""
    try:
        fit = IntentFit.model_validate(raw)
    except ValidationError as exc:
        return IntentFitOutcome(
            schema_valid=False,
            verdict="NEEDS_BUYER_CONFIRMATION",
            reason_code="UNCLEAR",
            reason="model output failed schema validation",
            confidence=0.0,
            floored=True,
            detail=str(exc)[:500],
        )

    floor_verdict = "PASS"
    if fit.confidence < min_confidence:
        floor_verdict = "NEEDS_BUYER_CONFIRMATION"
    if injection_suspected:
        floor_verdict = "NEEDS_BUYER_CONFIRMATION"

    final_verdict = tighten_only(fit.verdict, floor_verdict)
    floored = final_verdict != fit.verdict

    return IntentFitOutcome(
        schema_valid=True,
        verdict=final_verdict,
        reason_code=fit.reason_code,
        reason=fit.reason,
        confidence=fit.confidence,
        floored=floored,
        detail="floored by deterministic gate" if floored else "ok",
    )


def tighten_only(raw_verdict: str, floor_verdict: str) -> str:
    """Return whichever of `raw_verdict`/`floor_verdict` is MORE restrictive. Enforces
    the tighten-only invariant in code (build spec section 4) rather than trusting the
    model/prompt alone -- this is the actual security boundary, not prompt wording."""
    raw_rank = _VERDICT_RANK.get(raw_verdict)
    floor_rank = _VERDICT_RANK.get(floor_verdict)
    if raw_rank is None or floor_rank is None:
        # Unknown verdict value: fail closed to the most restrictive outcome.
        return "REJECT_WITH_REASON"
    return raw_verdict if raw_rank >= floor_rank else floor_verdict
