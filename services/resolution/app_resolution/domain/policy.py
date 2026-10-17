"""Deterministic policy engine: input facts, config, decision types, the three illustrative rules and the decision table.

Implements resolution/spec.md section 4 (policy engine, P1-P3 rules, decision table D0-D10) and
the AI boundary (AI never sets amounts; any missing fact fails closed to HUMAN_REVIEW).
Pure module: `decide` takes `now` as an argument; no I/O, no clock, no randomness.
All three rules are labelled ILLUSTRATIVE in UI/docs (brief values, not legal terms).
Scaffold only: rule and decide bodies are yours to write.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app_resolution.domain.states import CaseKind

_EVIDENCE_KINDS: frozenset[CaseKind] = frozenset(
    {CaseKind.DAMAGED, CaseKind.WRONG_ITEM, CaseKind.NOT_AS_DESCRIBED}
)
_PROTECTION_KINDS: frozenset[CaseKind] = frozenset({CaseKind.LATE, CaseKind.LOST})

# --- Illustrative policy constants (spec s4 table; config overrides at runtime) ---

# P1: ~USD 50 (brief, illustrative). Integer minor units (cents). Config: PS_RESOLUTION_POLICY_REFUND_CAP_MINOR.
POLICY_REFUND_CAP_MINOR_DEFAULT: int = 5000
POLICY_CURRENCY_DEFAULT: str = "USD"

# P2: category exclusions. PLACEHOLDER: empty until the product owner defines the list.
# Config: PS_RESOLUTION_POLICY_EXCLUDED_CATEGORIES (CSV). Do not hardcode real categories here.
POLICY_EXCLUDED_CATEGORIES_DEFAULT: frozenset[str] = frozenset()

# P3: velocity. "more than 2 completed refunds for the buyer in the last 30 days" -> HUMAN_REVIEW.
POLICY_VELOCITY_MAX_DEFAULT: int = 2  # strictly greater than this triggers P3
POLICY_VELOCITY_WINDOW_DAYS_DEFAULT: int = 30

# D0/D1 threshold for triage confidence (our own heuristic, I). Config: PS_RESOLUTION_TRIAGE_MIN_CONFIDENCE.
TRIAGE_MIN_CONFIDENCE_DEFAULT: float = 0.7


class PolicyClass(StrEnum):
    """Outcome class of decide(). Denial is NOT a class (spec s4: outcomes never include a denial)."""

    INSIDE_TERMS = "INSIDE_TERMS"
    OUTSIDE_TERMS = "OUTSIDE_TERMS"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    MERCHANT_OVERRIDE = (
        "MERCHANT_OVERRIDE"  # set by the merchant-action path, not by decide()
    )


class ReasonCode(StrEnum):
    """Stable reason codes (spec s4 table, s6, api.md). Buyer-visible text is looked up elsewhere."""

    FACT_UNAVAILABLE = "FACT_UNAVAILABLE"  # D0
    TERMS_INVALID = "TERMS_INVALID"  # D0
    TRIAGE_FAIL_CLOSED = "TRIAGE_FAIL_CLOSED"  # D1
    KIND_OTHER = "KIND_OTHER"  # D2
    CARRIER_DISAGREES = "CARRIER_DISAGREES"  # D3
    POLICY_CATEGORY = "POLICY_CATEGORY"  # D4 / P2
    POLICY_VELOCITY = "POLICY_VELOCITY"  # D5 / P3
    POLICY_CAP = "POLICY_CAP"  # D6 / P1
    NEEDS_EVIDENCE = "NEEDS_EVIDENCE"  # D7
    IN_TERMS = "IN_TERMS"  # D8
    OUT_OF_TERMS_AMOUNT = "OUT_OF_TERMS_AMOUNT"  # D9
    OUT_OF_TERMS_KIND = "OUT_OF_TERMS_KIND"  # D9
    OUT_OF_TERMS_WINDOW = "OUT_OF_TERMS_WINDOW"  # D9
    DEFAULT_DENY_TO_HUMAN = "DEFAULT_DENY_TO_HUMAN"  # D10
    UNSUPPORTED_TERMS = "UNSUPPORTED_TERMS"  # v1: non full-order terms rule


@dataclass(frozen=True, slots=True)
class PolicyConfig:
    """Config snapshot used by one decision. policy_version is pinned on every Decision."""

    policy_version: str  # PS_RESOLUTION_POLICY_VERSION
    refund_cap_minor: int  # P1
    excluded_categories: frozenset[str]  # P2
    velocity_max: int  # P3
    velocity_window_days: int  # P3
    triage_min_confidence: float  # D1


@dataclass(frozen=True, slots=True)
class TermsSnapshot:
    """Mandate terms copied into the case at open (spec s2 terms_snapshot). Read-only here."""

    kinds_covered: frozenset[CaseKind]
    max_refund_minor: int
    window_hold_days: (
        int  # protection window length as declared in terms (I: exact field name TBD)
    )
    rule: str  # "FULL_ORDER" in v1; anything else -> UNSUPPORTED_TERMS (spec s4)


@dataclass(frozen=True, slots=True)
class CaptureFacts:
    """Capture facts read fresh from checkout/adapter (spec s4 'capture')."""

    capture_id: str
    status: str  # COMPLETED | PARTIALLY_REFUNDED (spec s6 check 4)
    amount_minor: int
    refunded_total_minor: int
    currency: str


@dataclass(frozen=True, slots=True)
class DecisionFacts:
    """Everything decide() may look at. Assembled by a use case from fresh reads, then frozen (spec s4)."""

    kind: CaseKind
    triage_ok: bool
    triage_confidence: float
    injection_suspected: bool
    carrier_status: str | None  # None = tracking fact unavailable (D0)
    carrier_agrees: bool | None  # None = not evaluated (D0)
    terms: TermsSnapshot | None  # None = terms unavailable (D0)
    mandate_hash_valid: bool
    protected_until: datetime | None
    case_opened_at: datetime
    now: datetime  # passed in; decide() never reads a clock
    capture: CaptureFacts | None
    item_categories: frozenset[str]
    buyer_completed_refunds_in_window: int | None  # None = count unavailable (D0)


@dataclass(frozen=True, slots=True)
class Reason:
    """One reason attached to a Decision. text is looked up by code, never free text."""

    code: ReasonCode


@dataclass(frozen=True, slots=True)
class Decision:
    """Output of decide(). Stored in policy_decisions with a hash of the facts (spec s4)."""

    klass: PolicyClass
    reasons: tuple[Reason, ...]
    amount_minor: int | None  # None when no amount can be derived (fail-closed paths)
    currency: str | None
    policy_version: str
    facts_hash: (
        str  # SHA-256 over canonical facts; computed by the use case, carried here
    )


def rule_refund_cap(amount_minor: int, cfg: PolicyConfig) -> ReasonCode | None:
    """P1: return POLICY_CAP when amount_minor > cfg.refund_cap_minor, else None.

    Inputs: derived amount (server-side, full-order rule) and config.
    Output: ReasonCode.POLICY_CAP on a hit, None otherwise.
    Edge cases: equal to the cap is NOT a hit (boundary value test, sprint S3-04).
    """
    if amount_minor > cfg.refund_cap_minor:
        return ReasonCode.POLICY_CAP
    return None


def rule_category_exclusion(
    item_categories: frozenset[str], cfg: PolicyConfig
) -> ReasonCode | None:
    """P2: return POLICY_CATEGORY if any item category is in cfg.excluded_categories, else None.

    Inputs: categories of the captured items, excluded set from config.
    Output: ReasonCode.POLICY_CATEGORY on a hit, None otherwise.
    Edge cases: empty excluded set never hits; empty item set never hits.
    """
    if item_categories & cfg.excluded_categories:
        return ReasonCode.POLICY_CATEGORY
    return None


def rule_buyer_velocity(
    completed_in_window: int | None, cfg: PolicyConfig
) -> ReasonCode | None:
    """P3: return POLICY_VELOCITY when completed refunds in the window exceed velocity_max, else None.

    Inputs: count of COMPLETED refund_attempts for this buyer in the last window_days (demo clock),
            or None when the count could not be read.
    Output: ReasonCode.POLICY_VELOCITY on a hit; None when not exceeded.
    Edge cases: None input is a fact failure -> caller maps to FACT_UNAVAILABLE (D0), never a pass.
            Brief rule: 2 refunds allowed, the 3rd triggers review (boundary test, sprint S3-04).
    """
    if completed_in_window is None:
        return None
    if completed_in_window > cfg.velocity_max:
        return ReasonCode.POLICY_VELOCITY
    return None


def decide(facts: DecisionFacts, cfg: PolicyConfig) -> Decision:
    """Apply the D0-D10 decision table (first matching row wins) and return a Decision.

    Inputs: frozen facts and config. No I/O, no clock, no randomness.
    Output: Decision with klass, reasons, amount_minor/currency (from capture, server-side only).
    Rules: D0 missing/stale/errored facts or invalid mandate hash -> HUMAN_REVIEW (fail closed);
    D1 triage not ok / low confidence / injection -> HUMAN_REVIEW; D2 kind OTHER -> HUMAN_REVIEW;
    D3 carrier disagrees -> HUMAN_REVIEW; D4 P2; D5 P3; D6 P1; D7 DAMAGED/WRONG_ITEM/NOT_AS_DESCRIBED
    -> HUMAN_REVIEW NEEDS_EVIDENCE; D8 LATE/LOST covered, amount <= max, opened before protected_until
    -> INSIDE_TERMS; D9 LATE/LOST but over terms max, kind not covered, or outside window -> OUTSIDE_TERMS;
    D10 otherwise HUMAN_REVIEW. Same inputs must always give the same Decision.
    Edge cases: UNSUPPORTED_TERMS (rule != FULL_ORDER) -> HUMAN_REVIEW; decisions never deny.
    """

    def _human_review(reason: ReasonCode) -> Decision:
        return Decision(
            klass=PolicyClass.HUMAN_REVIEW,
            reasons=(Reason(reason),),
            amount_minor=None,
            currency=None,
            policy_version=cfg.policy_version,
            facts_hash=_facts_hash(facts),
        )

    # D0: required facts missing/stale/errored, or invalid mandate hash (fail closed).
    if facts.terms is None:
        return _human_review(ReasonCode.FACT_UNAVAILABLE)
    if facts.capture is None:
        return _human_review(ReasonCode.FACT_UNAVAILABLE)
    if facts.buyer_completed_refunds_in_window is None:
        return _human_review(ReasonCode.FACT_UNAVAILABLE)
    if not facts.mandate_hash_valid:
        return _human_review(ReasonCode.TERMS_INVALID)
    if facts.kind in _PROTECTION_KINDS and (
        facts.carrier_agrees is None or facts.protected_until is None
    ):
        return _human_review(ReasonCode.FACT_UNAVAILABLE)
    if facts.terms.rule != "FULL_ORDER":
        return _human_review(ReasonCode.UNSUPPORTED_TERMS)

    # D1: triage must be ok, confident enough, and not injection-suspected (fail closed).
    if (
        not facts.triage_ok
        or facts.triage_confidence < cfg.triage_min_confidence
        or facts.injection_suspected
    ):
        return _human_review(ReasonCode.TRIAGE_FAIL_CLOSED)

    # D2: kind OTHER always needs a human.
    if facts.kind == CaseKind.OTHER:
        return _human_review(ReasonCode.KIND_OTHER)

    # D3: our own carrier facts disagree with a LATE/LOST claim.
    if facts.kind in _PROTECTION_KINDS and facts.carrier_agrees is False:
        return _human_review(ReasonCode.CARRIER_DISAGREES)

    # Server-derived amount (full-order rule, spec s4): capture total minus refunded total.
    amount_minor = facts.capture.amount_minor - facts.capture.refunded_total_minor
    currency = facts.capture.currency

    # D4: P2 category exclusion.
    category_hit = rule_category_exclusion(facts.item_categories, cfg)
    if category_hit is not None:
        return _human_review(category_hit)

    # D5: P3 buyer velocity.
    velocity_hit = rule_buyer_velocity(facts.buyer_completed_refunds_in_window, cfg)
    if velocity_hit is not None:
        return _human_review(velocity_hit)

    # D6: P1 refund cap.
    cap_hit = rule_refund_cap(amount_minor, cfg)
    if cap_hit is not None:
        return _human_review(cap_hit)

    # D7: evidence-needing kinds always go to a human (reviewer may then propose).
    if facts.kind in _EVIDENCE_KINDS:
        return _human_review(ReasonCode.NEEDS_EVIDENCE)

    # D8/D9 apply only to LATE/LOST (D2/D7 already handled OTHER and evidence kinds).
    if facts.kind in _PROTECTION_KINDS:
        covered = facts.kind in facts.terms.kinds_covered
        within_cap = amount_minor <= facts.terms.max_refund_minor
        within_window = facts.case_opened_at <= facts.protected_until  # type: ignore[operator]

        if covered and within_cap and within_window:
            return Decision(
                klass=PolicyClass.INSIDE_TERMS,
                reasons=(Reason(ReasonCode.IN_TERMS),),
                amount_minor=amount_minor,
                currency=currency,
                policy_version=cfg.policy_version,
                facts_hash=_facts_hash(facts),
            )

        if not covered:
            out_reason = ReasonCode.OUT_OF_TERMS_KIND
        elif not within_window:
            out_reason = ReasonCode.OUT_OF_TERMS_WINDOW
        else:
            out_reason = ReasonCode.OUT_OF_TERMS_AMOUNT

        return Decision(
            klass=PolicyClass.OUTSIDE_TERMS,
            reasons=(Reason(out_reason),),
            amount_minor=amount_minor,
            currency=currency,
            policy_version=cfg.policy_version,
            facts_hash=_facts_hash(facts),
        )

    # D10: default deny to human.
    return _human_review(ReasonCode.DEFAULT_DENY_TO_HUMAN)


def _facts_hash(facts: DecisionFacts) -> str:
    """SHA-256 over a canonical JSON snapshot of the facts decide() actually used.

    Not a port of proposal_hash (different fields); purely a reproducibility aid for
    policy_decisions.facts_hash (spec s4 'stored ... with the full facts hash').
    """
    raw = {
        "kind": facts.kind.value,
        "triage_ok": facts.triage_ok,
        "triage_confidence": facts.triage_confidence,
        "injection_suspected": facts.injection_suspected,
        "carrier_status": facts.carrier_status,
        "carrier_agrees": facts.carrier_agrees,
        "terms": None
        if facts.terms is None
        else {
            "kinds_covered": sorted(k.value for k in facts.terms.kinds_covered),
            "max_refund_minor": facts.terms.max_refund_minor,
            "window_hold_days": facts.terms.window_hold_days,
            "rule": facts.terms.rule,
        },
        "mandate_hash_valid": facts.mandate_hash_valid,
        "protected_until": None
        if facts.protected_until is None
        else facts.protected_until.isoformat(),
        "case_opened_at": facts.case_opened_at.isoformat(),
        "now": facts.now.isoformat(),
        "capture": None
        if facts.capture is None
        else {
            "capture_id": facts.capture.capture_id,
            "status": facts.capture.status,
            "amount_minor": facts.capture.amount_minor,
            "refunded_total_minor": facts.capture.refunded_total_minor,
            "currency": facts.capture.currency,
        },
        "item_categories": sorted(facts.item_categories),
        "buyer_completed_refunds_in_window": facts.buyer_completed_refunds_in_window,
    }
    canonical = json.dumps(
        raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def config_from_settings(
    settings_values: Mapping[str, str | int | float | bool],
) -> PolicyConfig:
    """Build a PolicyConfig from PS_RESOLUTION_POLICY_* settings values.

    Inputs: flat mapping of setting names to values (caller reads app/settings.py).
    Output: PolicyConfig. Edge cases: missing keys must raise, never silently default in production.
    """

    def _require(key: str) -> str | int | float | bool:
        if key not in settings_values:
            raise KeyError(f"missing required policy setting: {key}")
        return settings_values[key]

    excluded_raw = _require("excluded_categories")
    excluded: frozenset[str]
    if isinstance(excluded_raw, str):
        excluded = frozenset(c.strip() for c in excluded_raw.split(",") if c.strip())
    elif isinstance(excluded_raw, (list, tuple, frozenset, set)):
        excluded = frozenset(str(c) for c in excluded_raw)
    else:
        excluded = frozenset()

    return PolicyConfig(
        policy_version=str(_require("policy_version")),
        refund_cap_minor=int(_require("refund_cap_minor")),
        excluded_categories=excluded,
        velocity_max=int(_require("velocity_max")),
        velocity_window_days=int(_require("velocity_window_days")),
        triage_min_confidence=float(_require("triage_min_confidence")),
    )
