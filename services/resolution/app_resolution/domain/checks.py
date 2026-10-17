"""The 9 ordered pre-refund checks: IDs, result types, and the pure amount-bounds check as the pattern.

Implements resolution/spec.md section 6 (9 ordered pre-refund checks, fail closed). Pure checks
take facts and return a CheckResult; the orchestration (fresh reads, transaction for check 9,
treating exceptions as FAIL) lives in usecases/execute_refund.py. Scaffold only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from app_resolution.domain.policy import ReasonCode


class CheckId(IntEnum):
    """Check numbers exactly as in spec s6 table. Run order = numeric order, stop at first failure."""

    KILL_SWITCH = 1
    AUTHORIZATION_VALID = 2
    TERMS_INTEGRITY = 3
    CAPTURE_IDENTITY = 4
    AMOUNT_BOUNDS = 5
    POLICY_REEVALUATION = 6
    NO_PRIOR_MONEY_ACTION = 7
    PROBLEM_STILL_TRUE = 8
    DURABLE_INTENT = 9


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Result of one check, written to policy_decisions.checks jsonb (spec s6)."""

    check: CheckId
    passed: bool
    reason_code: ReasonCode | None  # set on failure only
    detail_code: str | None  # stable short code, never free text


@dataclass(frozen=True, slots=True)
class CheckReport:
    """All results up to and including the first failure (spec s6 'stops at the first failure')."""

    results: tuple[CheckResult, ...]
    passed: bool


@dataclass(frozen=True, slots=True)
class AmountFacts:
    """Facts for check 5 (amount bounds). All money in integer minor units (spec s6)."""

    proposal_amount_minor: int
    requested_amount_minor: int
    remaining_refundable_minor: int  # capture amount - refunded total, read fresh
    terms_max_refund_minor: int
    explicit_buyer_approval_or_override: (
        bool  # bypasses the terms max only when True (spec s6 check 5)
    )
    adapter_per_call_ceiling_minor: int


def check_amount_bounds(facts: AmountFacts) -> CheckResult:
    """Check 5: amount is a positive integer, equals the proposal, and is within every bound.

    Inputs: AmountFacts from the proposal row and fresh capture/adapter reads.
    Output: CheckResult(check=AMOUNT_BOUNDS, ...). Fail -> HUMAN_REVIEW.
    Rules (spec s6 check 5): integer > 0; == proposal amount; <= remaining refundable;
    <= terms max unless explicit buyer approval/override; <= adapter per-call ceiling.
    Edge cases: any exception or missing value must be FAIL (caller wraps in try/except).
    """
    try:
        amount = facts.requested_amount_minor
        if not isinstance(amount, int) or amount <= 0:
            return CheckResult(
                CheckId.AMOUNT_BOUNDS,
                False,
                ReasonCode.FACT_UNAVAILABLE,
                "AMOUNT_NOT_POSITIVE",
            )
        if amount != facts.proposal_amount_minor:
            return CheckResult(
                CheckId.AMOUNT_BOUNDS, False, None, "AMOUNT_NOT_EQUAL_PROPOSAL"
            )
        if amount > facts.remaining_refundable_minor:
            return CheckResult(
                CheckId.AMOUNT_BOUNDS,
                False,
                None,
                "AMOUNT_EXCEEDS_REMAINING_REFUNDABLE",
            )
        if (
            not facts.explicit_buyer_approval_or_override
            and amount > facts.terms_max_refund_minor
        ):
            return CheckResult(
                CheckId.AMOUNT_BOUNDS, False, None, "AMOUNT_EXCEEDS_TERMS_MAX"
            )
        if amount > facts.adapter_per_call_ceiling_minor:
            return CheckResult(
                CheckId.AMOUNT_BOUNDS, False, None, "AMOUNT_EXCEEDS_ADAPTER_CEILING"
            )
        return CheckResult(CheckId.AMOUNT_BOUNDS, True, None, None)
    except Exception:  # noqa: BLE001 - any error on a money check is a fail, never a pass
        return CheckResult(
            CheckId.AMOUNT_BOUNDS,
            False,
            ReasonCode.FACT_UNAVAILABLE,
            "AMOUNT_BOUNDS_ERROR",
        )


# ---------------------------------------------------------------------------
# Checks 1-4 and 6-8 (spec s6). Each is pure: facts in, CheckResult out. Check 9
# (durable intent) is the only check that writes, so it lives in usecases/execute_refund.py,
# not here. Reason codes reuse the closed ReasonCode enum where semantically apt; the
# stable `detail_code` (never free text) carries check-specific detail (spec s6 CheckResult).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class KillSwitchFacts:
    """Facts for check 1 (spec s6). Absent/unreadable flag counts as frozen (fail closed)."""

    refunds_frozen: bool | None  # None = unreadable -> treated as frozen
    mandate_frozen: bool = False
    merchant_frozen: bool = False


def check_kill_switch(facts: KillSwitchFacts) -> CheckResult:
    """Check 1: pass only when the global/mandate/merchant freeze flags are all readably false."""
    if facts.refunds_frozen is None or facts.refunds_frozen:
        return CheckResult(CheckId.KILL_SWITCH, False, None, "REFUNDS_FROZEN")
    if facts.mandate_frozen or facts.merchant_frozen:
        return CheckResult(CheckId.KILL_SWITCH, False, None, "REFUNDS_FROZEN")
    return CheckResult(CheckId.KILL_SWITCH, True, None, None)


@dataclass(frozen=True, slots=True)
class AuthorizationFacts:
    """Facts for check 2 (spec s6): case state, approval basis, offer/hash state."""

    case_state: str  # CaseState.value; must be APPROVED
    approval_basis_present: bool  # preauth, accepted offer, or redeemed approval
    offer_active: bool  # the offer this approval is for has not been superseded/expired
    stored_hash_matches: bool  # recomputed proposal_hash == stored (spec s5)


def check_authorization_valid(facts: AuthorizationFacts) -> CheckResult:
    """Check 2: case must be APPROVED with a live, hash-matching approval basis."""
    if facts.case_state != "APPROVED":
        return CheckResult(
            CheckId.AUTHORIZATION_VALID, False, None, "CASE_NOT_APPROVED"
        )
    if not facts.approval_basis_present:
        return CheckResult(
            CheckId.AUTHORIZATION_VALID, False, None, "NO_APPROVAL_BASIS"
        )
    if not facts.offer_active:
        return CheckResult(CheckId.AUTHORIZATION_VALID, False, None, "OFFER_NOT_ACTIVE")
    if not facts.stored_hash_matches:
        return CheckResult(
            CheckId.AUTHORIZATION_VALID, False, None, "PROPOSAL_HASH_MISMATCH"
        )
    return CheckResult(CheckId.AUTHORIZATION_VALID, True, None, None)


@dataclass(frozen=True, slots=True)
class TermsIntegrityFacts:
    """Facts for check 3 (spec s6): fresh mandate terms vs the case's frozen snapshot."""

    fresh_terms_hash: str | None  # None = mandate unreachable
    fresh_terms_hmac_valid: bool
    stored_terms_hash: str
    decision_policy_version: str
    current_policy_version: str


def check_terms_integrity(facts: TermsIntegrityFacts) -> CheckResult:
    """Check 3: mandate-returned terms hash/HMAC must match the frozen snapshot and policy version."""
    if facts.fresh_terms_hash is None:
        return CheckResult(
            CheckId.TERMS_INTEGRITY,
            False,
            ReasonCode.FACT_UNAVAILABLE,
            "MANDATE_UNREACHABLE",
        )
    if not facts.fresh_terms_hmac_valid:
        return CheckResult(
            CheckId.TERMS_INTEGRITY,
            False,
            ReasonCode.TERMS_INVALID,
            "TERMS_HMAC_INVALID",
        )
    if facts.fresh_terms_hash != facts.stored_terms_hash:
        return CheckResult(
            CheckId.TERMS_INTEGRITY,
            False,
            ReasonCode.TERMS_INVALID,
            "TERMS_HASH_MISMATCH",
        )
    if facts.decision_policy_version != facts.current_policy_version:
        return CheckResult(
            CheckId.TERMS_INTEGRITY, False, None, "POLICY_VERSION_CHANGED"
        )
    return CheckResult(CheckId.TERMS_INTEGRITY, True, None, None)


@dataclass(frozen=True, slots=True)
class CaptureIdentityFacts:
    """Facts for check 4 (spec s6): fresh capture read vs the case/order it claims to belong to."""

    capture_order_matches: bool
    custom_id_matches_mandate: bool
    capture_status: str  # must be COMPLETED or PARTIALLY_REFUNDED
    capture_currency: str
    proposal_currency: str


_CAPTURE_STATUSES_OK: frozenset[str] = frozenset({"COMPLETED", "PARTIALLY_REFUNDED"})


def check_capture_identity(facts: CaptureIdentityFacts) -> CheckResult:
    """Check 4: capture must belong to this order/mandate, be refundable, and match currency."""
    if not facts.capture_order_matches:
        return CheckResult(
            CheckId.CAPTURE_IDENTITY, False, None, "CAPTURE_ORDER_MISMATCH"
        )
    if not facts.custom_id_matches_mandate:
        return CheckResult(CheckId.CAPTURE_IDENTITY, False, None, "CUSTOM_ID_MISMATCH")
    if facts.capture_status not in _CAPTURE_STATUSES_OK:
        return CheckResult(
            CheckId.CAPTURE_IDENTITY, False, None, "CAPTURE_STATUS_NOT_REFUNDABLE"
        )
    if facts.capture_currency != facts.proposal_currency:
        return CheckResult(CheckId.CAPTURE_IDENTITY, False, None, "CURRENCY_MISMATCH")
    return CheckResult(CheckId.CAPTURE_IDENTITY, True, None, None)


@dataclass(frozen=True, slots=True)
class PolicyReevaluationFacts:
    """Facts for check 6 (spec s6): re-running decide() on fresh facts must agree with the offer."""

    fresh_klass: str  # PolicyClass.value from a fresh decide() call
    offer_klass: str  # PolicyClass.value the offer/decision was created with
    is_merchant_override: bool
    decision_policy_version: str
    current_policy_version: str


def check_policy_reevaluation(facts: PolicyReevaluationFacts) -> CheckResult:
    """Check 6: fresh decide() must still agree (or the offer is a merchant override)."""
    if facts.decision_policy_version != facts.current_policy_version:
        return CheckResult(
            CheckId.POLICY_REEVALUATION, False, None, "POLICY_VERSION_CHANGED"
        )
    if facts.is_merchant_override:
        return CheckResult(CheckId.POLICY_REEVALUATION, True, None, None)
    if facts.fresh_klass != facts.offer_klass:
        return CheckResult(
            CheckId.POLICY_REEVALUATION, False, None, "POLICY_CLASS_CHANGED"
        )
    return CheckResult(CheckId.POLICY_REEVALUATION, True, None, None)


@dataclass(frozen=True, slots=True)
class PriorMoneyActionFacts:
    """Facts for check 7 (spec s6): at most one refund attempt per case, one live per order."""

    attempt_exists_for_case: bool
    live_attempt_exists_for_order: (
        bool  # another case on the same order already has one
    )


def check_no_prior_money_action(facts: PriorMoneyActionFacts) -> CheckResult:
    """Check 7: fail if this case or its order already has a refund attempt in flight/done."""
    if facts.attempt_exists_for_case:
        return CheckResult(
            CheckId.NO_PRIOR_MONEY_ACTION, False, None, "ATTEMPT_EXISTS_FOR_CASE"
        )
    if facts.live_attempt_exists_for_order:
        return CheckResult(
            CheckId.NO_PRIOR_MONEY_ACTION, False, None, "LIVE_ATTEMPT_EXISTS_FOR_ORDER"
        )
    return CheckResult(CheckId.NO_PRIOR_MONEY_ACTION, True, None, None)


@dataclass(frozen=True, slots=True)
class ProblemStillTrueFacts:
    """Facts for check 8 (spec s6): the tracking problem must still hold, right before sending money."""

    kind: str  # CaseKind.value
    carrier_status: str | None  # None = tracking fact unavailable
    window_held: bool


def check_problem_still_true(facts: ProblemStillTrueFacts) -> CheckResult:
    """Check 8: LATE/LOST claims must not have resolved themselves (e.g. delivered) since approval."""
    if not facts.window_held:
        return CheckResult(CheckId.PROBLEM_STILL_TRUE, False, None, "WINDOW_NOT_HELD")
    if facts.kind in ("LATE", "LOST"):
        if facts.carrier_status is None:
            return CheckResult(
                CheckId.PROBLEM_STILL_TRUE,
                False,
                ReasonCode.FACT_UNAVAILABLE,
                "CARRIER_FACT_UNAVAILABLE",
            )
        if facts.carrier_status == "DELIVERED":
            return CheckResult(
                CheckId.PROBLEM_STILL_TRUE, False, None, "PACKAGE_NOW_DELIVERED"
            )
    return CheckResult(CheckId.PROBLEM_STILL_TRUE, True, None, None)
