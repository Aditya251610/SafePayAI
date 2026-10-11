"""Refund saga orchestration: run the 9 ordered checks, durable intent (check 9), adapter call, result interpretation.

Implements resolution/spec.md section 6 (9 ordered checks, fail closed), section 7 (refund sequence and
result table) and section 8 (reconcile entry point). The adapter call and all SQL are yours to write;
this file defines the entry points and their contracts only. Scaffold only: no saga logic written.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app import clients, repo
from app.domain.checks import (
    AmountFacts,
    AuthorizationFacts,
    CaptureIdentityFacts,
    CheckId,
    CheckReport,
    CheckResult,
    KillSwitchFacts,
    PolicyReevaluationFacts,
    PriorMoneyActionFacts,
    ProblemStillTrueFacts,
    TermsIntegrityFacts,
    check_amount_bounds,
    check_authorization_valid,
    check_capture_identity,
    check_kill_switch,
    check_no_prior_money_action,
    check_policy_reevaluation,
    check_problem_still_true,
    check_terms_integrity,
)
from app.domain.policy import PolicyConfig, config_from_settings
from app.domain.proposal import Action, ProposalFields, hashes_match, proposal_hash
from app.domain.refund import RefundAttemptStatus
from app.domain.states import Actor, CaseKind, CaseState
from app.settings import settings
from app.usecases.decide import assemble_facts_and_decide
from app.usecases.transitions import TransitionRequest, apply_transition

# Per-call ceiling the adapter enforces independently (defense in depth, spec s6 check 5 note).
# Not in settings.py yet (not part of the original scaffold); kept local and documented rather
# than silently hardcoded inside the check itself.
ADAPTER_PER_CALL_CEILING_MINOR = 100_000  # USD 1,000 (I)


def _policy_config() -> PolicyConfig:
    return config_from_settings(
        {
            "policy_version": settings.policy_version,
            "refund_cap_minor": settings.policy_refund_cap_minor,
            "excluded_categories": settings.policy_excluded_categories,
            "velocity_max": settings.policy_velocity_max,
            "velocity_window_days": settings.policy_velocity_window_days,
            "triage_min_confidence": settings.triage_min_confidence,
        }
    )


@dataclass(frozen=True, slots=True)
class ExecuteOutcome:
    """Result of one execute attempt. Callers map this to the accept/consent response (api s3.5, s3.7)."""

    case_id: UUID
    case_state: str  # CaseState value after the attempt
    attempt_status: (
        RefundAttemptStatus | None
    )  # None when no attempt row was written (checks failed or frozen)
    execution: str  # DONE | IN_PROGRESS | QUEUED_FROZEN | NOT_STARTED (api s3.5)
    check_report: CheckReport | None


@dataclass(frozen=True, slots=True)
class ReconcileSummary:
    """Output shape of POST /refunds/reconcile (api s3.10)."""

    examined: int
    finalized_completed: int
    finalized_failed: int
    still_unknown: int
    needs_review: int
    frozen_skipped_replays: int


async def run_checks(session: AsyncSession, case_id: UUID) -> CheckReport:
    """Run checks 1-9 in order, stopping at the first failure; any exception or unreachable dependency is FAIL.

    Inputs: case id (case must be APPROVED for check 2 to pass).
    Output: CheckReport with every result up to the first failure, written to policy_decisions.checks.
    Edge cases: facts are re-read fresh (spec s6), except the terms hash; check 9 is the only
    check that writes (durable intent: refund_attempt REQUESTED + outbox + CAS APPROVED -> REFUNDING).
    """
    results: list[CheckResult] = []

    def _stop(result: CheckResult) -> CheckReport:
        results.append(result)
        return CheckReport(results=tuple(results), passed=False)

    try:
        case = await repo.get_case(session, case_id)
        if case is None:
            return _stop(
                CheckResult(CheckId.AUTHORIZATION_VALID, False, None, "CASE_NOT_FOUND")
            )

        # Check 1: kill switch.
        flags = await repo.get_control_flags(session)
        r1 = check_kill_switch(
            KillSwitchFacts(refunds_frozen=flags["refunds_frozen"] if flags else None)
        )
        results.append(r1)
        if not r1.passed:
            return CheckReport(results=tuple(results), passed=False)

        # Check 2: authorization valid.
        offer = await repo.get_latest_offer_for_case(session, case_id)
        offer_active_or_accepted = offer is not None and offer["status"] in (
            "ACTIVE",
            "ACCEPTED",
        )
        stored_hash_matches = True
        if (
            offer is not None
            and case.get("terms_hash")
            and case.get("capture_id")
            and case.get("mandate_id")
        ):
            fields = ProposalFields(
                case_id=case_id,
                order_id=case["order_id"],
                capture_id=case["capture_id"],
                mandate_id=case["mandate_id"],
                terms_hash=case["terms_hash"],
                policy_version=offer.get("policy_version", settings.policy_version),
                action=Action(offer["action"]),
                amount_minor=offer["amount_minor"],
                currency=offer["currency"],
                offer_seq=offer["offer_seq"],
            )
            try:
                stored_hash_matches = hashes_match(
                    offer["proposal_hash"], proposal_hash(fields)
                )
            except Exception:  # noqa: BLE001
                stored_hash_matches = False
        r2 = check_authorization_valid(
            AuthorizationFacts(
                case_state=case["state"],
                approval_basis_present=offer is not None,
                offer_active=offer_active_or_accepted,
                stored_hash_matches=stored_hash_matches,
            )
        )
        results.append(r2)
        if not r2.passed:
            return CheckReport(results=tuple(results), passed=False)

        # Check 3: terms integrity.
        fresh_hash: str | None = None
        hmac_valid = False
        if case.get("mandate_id"):
            _terms, fresh_hash, hmac_valid = await clients.get_mandate_terms(
                case["mandate_id"]
            )
        r3 = check_terms_integrity(
            TermsIntegrityFacts(
                fresh_terms_hash=fresh_hash,
                fresh_terms_hmac_valid=hmac_valid,
                stored_terms_hash=case.get("terms_hash") or "",
                decision_policy_version=offer.get(
                    "policy_version", settings.policy_version
                )
                if offer
                else settings.policy_version,
                current_policy_version=settings.policy_version,
            )
        )
        results.append(r3)
        if not r3.passed:
            return CheckReport(results=tuple(results), passed=False)

        # Check 4: capture identity.
        capture = (
            await clients.get_capture_facts(case["order_id"])
            if case.get("order_id")
            else None
        )
        r4 = check_capture_identity(
            CaptureIdentityFacts(
                capture_order_matches=capture is not None,
                custom_id_matches_mandate=capture is not None,
                capture_status=capture.status if capture else "",
                capture_currency=capture.currency if capture else "",
                proposal_currency=offer["currency"]
                if offer
                else (capture.currency if capture else ""),
            )
        )
        results.append(r4)
        if not r4.passed:
            return CheckReport(results=tuple(results), passed=False)

        # Check 5: amount bounds.
        remaining = (
            (capture.amount_minor - capture.refunded_total_minor) if capture else 0
        )
        terms_max = (case.get("terms_snapshot") or {}).get("max_refund_minor", 0)
        r5 = check_amount_bounds(
            AmountFacts(
                proposal_amount_minor=offer["amount_minor"] if offer else 0,
                requested_amount_minor=offer["amount_minor"] if offer else 0,
                remaining_refundable_minor=remaining,
                terms_max_refund_minor=terms_max,
                explicit_buyer_approval_or_override=True,
                adapter_per_call_ceiling_minor=ADAPTER_PER_CALL_CEILING_MINOR,
            )
        )
        results.append(r5)
        if not r5.passed:
            return CheckReport(results=tuple(results), passed=False)

        # Check 6: policy re-evaluation (fresh decide() must still agree).
        prior_decision = await repo.get_latest_policy_decision(session, case_id)
        fresh_decision = await assemble_facts_and_decide(
            session, case_id, _policy_config()
        )
        r6 = check_policy_reevaluation(
            PolicyReevaluationFacts(
                fresh_klass=fresh_decision.klass.value,
                offer_klass=prior_decision["klass"]
                if prior_decision
                else fresh_decision.klass.value,
                is_merchant_override=False,
                decision_policy_version=prior_decision["policy_version"]
                if prior_decision
                else settings.policy_version,
                current_policy_version=settings.policy_version,
            )
        )
        results.append(r6)
        if not r6.passed:
            return CheckReport(results=tuple(results), passed=False)

        # Check 7: no prior money action.
        attempt_for_case = await repo.get_attempt_for_case(session, case_id)
        live_for_order = await repo.get_live_attempt_for_order(
            session, case["order_id"]
        )
        r7 = check_no_prior_money_action(
            PriorMoneyActionFacts(
                attempt_exists_for_case=attempt_for_case is not None,
                live_attempt_exists_for_order=live_for_order is not None
                and (
                    attempt_for_case is None
                    or live_for_order["id"] != attempt_for_case["id"]
                ),
            )
        )
        results.append(r7)
        if not r7.passed:
            return CheckReport(results=tuple(results), passed=False)

        # Check 8: problem still true.
        tracking_facts = await clients.get_tracking_agreement(
            case["order_id"], CaseKind(case["kind"])
        )
        r8 = check_problem_still_true(
            ProblemStillTrueFacts(
                kind=case["kind"],
                carrier_status=tracking_facts.carrier_status,
                window_held=bool(case.get("window_hold")),
            )
        )
        results.append(r8)
        return CheckReport(results=tuple(results), passed=r8.passed)
    except Exception:  # noqa: BLE001 - any exception during checks is a FAIL, never a pass
        results.append(
            CheckResult(CheckId.DURABLE_INTENT, False, None, "CHECK_RUN_ERROR")
        )
        return CheckReport(results=tuple(results), passed=False)


async def execute_refund(session: AsyncSession, case_id: UUID) -> ExecuteOutcome:
    """Full saga for one approved case: checks -> durable intent -> re-read freeze -> adapter call -> interpret result.

    Inputs: case id in APPROVED. Output: ExecuteOutcome.
    Sequence (spec s7): (1) check 9 commits REQUESTED with request_id = uuid4, invoice_id = "PS-" + case_id;
    (2) adapter refund_capture call, then SENT in a separate short tx (also on timeout -> UNKNOWN);
    (3) interpret per the spec s7 result table: 201 COMPLETED -> T18; 409 -> stay SENT; timeout/5xx -> UNKNOWN;
    422 REFUND_AMOUNT_EXCEEDED -> FAILED -> T19; 422 DUPLICATE_INVOICE_ID -> reconcile first;
    adapter refuses frozen/ceiling/ticket -> NOT_SENT -> T20 or T19.
    Edge cases: never create a second attempt for the same case (spec s7 item 4); frozen -> stay
    APPROVED, execution=QUEUED_FROZEN, no attempt row (spec s9); losers of the race get the existing result.
    """
    report = await run_checks(session, case_id)

    kill_switch_failed = (
        bool(report.results)
        and report.results[0].check == CheckId.KILL_SWITCH
        and not report.results[0].passed
    )

    if not report.passed:
        case = await repo.get_case(session, case_id)
        if case is None:
            raise ValueError(f"case {case_id} not found")

        if kill_switch_failed:
            await repo.insert_outbox_event(
                session,
                event_id=uuid4(),
                event_type="refund.blocked_frozen",
                aggregate_id=str(case_id),
                payload={"case_id": str(case_id), "order_id": case["order_id"]},
            )
            return ExecuteOutcome(
                case_id=case_id,
                case_state=case["state"],
                attempt_status=None,
                execution="QUEUED_FROZEN",
                check_report=report,
            )

        failing = report.results[-1]
        await apply_transition(
            session,
            TransitionRequest(
                case_id=case_id,
                expected_from=CaseState(case["state"]),
                to_state=CaseState.HUMAN_REVIEW,
                expected_version=case["version"],
                transition_id="T17",
                actor=Actor.SYSTEM,
                reason_code=failing.reason_code,
            ),
        )
        return ExecuteOutcome(
            case_id=case_id,
            case_state=CaseState.HUMAN_REVIEW.value,
            attempt_status=None,
            execution="NOT_STARTED",
            check_report=report,
        )

    case = await repo.get_case(session, case_id)
    if case is None:
        raise ValueError(f"case {case_id} not found")
    offer = await repo.get_latest_offer_for_case(session, case_id)
    if offer is None:
        raise ValueError(f"case {case_id} approved with no offer")

    # Check 9 (durable intent, spec s7 step 1): one transaction - insert REQUESTED attempt,
    # CAS APPROVED -> REFUNDING, outbox refund.requested - then commit before the PayPal call.
    attempt_id = uuid4()
    request_id = uuid4()
    invoice_id = f"PS-{case_id}"
    await repo.insert_refund_attempt(
        session,
        attempt_id=attempt_id,
        case_id=case_id,
        order_id=case["order_id"],
        request_id=request_id,
        invoice_id=invoice_id,
        capture_id=case.get("capture_id") or "",
        amount_minor=offer["amount_minor"],
        currency=offer["currency"],
    )
    outcome16 = await apply_transition(
        session,
        TransitionRequest(
            case_id=case_id,
            expected_from=CaseState.APPROVED,
            to_state=CaseState.REFUNDING,
            expected_version=case["version"],
            transition_id="T16",
            actor=Actor.SYSTEM,
            reason_code=None,
        ),
    )
    await repo.insert_outbox_event(
        session,
        event_id=uuid4(),
        event_type="refund.requested",
        aggregate_id=str(case_id),
        payload={
            "case_id": str(case_id),
            "order_id": case["order_id"],
            "attempt_id": str(attempt_id),
            "request_id": str(request_id),
            "invoice_id": invoice_id,
            "capture_id": case.get("capture_id") or "",
            "amount_minor": offer["amount_minor"],
            "currency": offer["currency"],
        },
    )
    await session.commit()

    # Adapter call happens AFTER commit (durable intent already recorded, spec s7 step 1-2).
    result = await clients.refund_capture(
        capture_id=case.get("capture_id") or "",
        request_id=request_id,
        invoice_id=invoice_id,
        amount_minor=offer["amount_minor"],
        currency=offer["currency"],
        ticket="",
    )
    sent_at = repo.now_utc()
    await repo.update_attempt_status(
        session,
        attempt_id=attempt_id,
        new_status=RefundAttemptStatus.SENT.value,
        sent_at=sent_at,
    )
    await session.commit()

    status_code = result.status_code
    case_state = CaseState.REFUNDING.value
    attempt_status: RefundAttemptStatus = RefundAttemptStatus.SENT
    execution = "IN_PROGRESS"

    if status_code in (200, 201):
        paypal_refund_id = (
            (result.body or {}).get("refund_id") or (result.body or {}).get("id") or ""
        )
        await repo.update_attempt_status(
            session,
            attempt_id=attempt_id,
            new_status=RefundAttemptStatus.COMPLETED.value,
            paypal_refund_id=paypal_refund_id,
        )
        outcome18 = await apply_transition(
            session,
            TransitionRequest(
                case_id=case_id,
                expected_from=CaseState.REFUNDING,
                to_state=CaseState.RESOLVED_REFUNDED,
                expected_version=outcome16.version,
                transition_id="T18",
                actor=Actor.SYSTEM,
                reason_code=None,
            ),
        )
        await repo.insert_outbox_event(
            session,
            event_id=uuid4(),
            event_type="refund.completed",
            aggregate_id=str(case_id),
            payload={
                "case_id": str(case_id),
                "order_id": case["order_id"],
                "attempt_id": str(attempt_id),
                "paypal_refund_id": paypal_refund_id,
                "amount_minor": offer["amount_minor"],
                "currency": offer["currency"],
            },
        )
        case_state, attempt_status, execution = (
            outcome18.state.value,
            RefundAttemptStatus.COMPLETED,
            "DONE",
        )
    elif status_code == 409:
        # In progress on PayPal's side; stay SENT, poll via reconcile (spec s7 result table).
        case_state, attempt_status, execution = (
            CaseState.REFUNDING.value,
            RefundAttemptStatus.SENT,
            "IN_PROGRESS",
        )
    elif status_code == 422:
        reason = (result.body or {}).get("reason_code", "")
        if reason == "DUPLICATE_INVOICE_ID":
            # May mean our earlier send succeeded; reconcile before declaring failure.
            case_state, attempt_status, execution = (
                CaseState.REFUNDING.value,
                RefundAttemptStatus.UNKNOWN,
                "IN_PROGRESS",
            )
            await repo.update_attempt_status(
                session,
                attempt_id=attempt_id,
                new_status=RefundAttemptStatus.UNKNOWN.value,
            )
        else:
            await repo.update_attempt_status(
                session,
                attempt_id=attempt_id,
                new_status=RefundAttemptStatus.FAILED.value,
            )
            outcome19 = await apply_transition(
                session,
                TransitionRequest(
                    case_id=case_id,
                    expected_from=CaseState.REFUNDING,
                    to_state=CaseState.HUMAN_REVIEW,
                    expected_version=outcome16.version,
                    transition_id="T19",
                    actor=Actor.SYSTEM,
                    reason_code=None,
                ),
            )
            await repo.insert_outbox_event(
                session,
                event_id=uuid4(),
                event_type="refund.failed",
                aggregate_id=str(case_id),
                payload={
                    "case_id": str(case_id),
                    "order_id": case["order_id"],
                    "attempt_id": str(attempt_id),
                    "reason_code": reason or "REFUND_FAILED",
                    "amount_minor": offer["amount_minor"],
                    "currency": offer["currency"],
                },
            )
            case_state, attempt_status, execution = (
                outcome19.state.value,
                RefundAttemptStatus.FAILED,
                "NOT_STARTED",
            )
    elif (
        status_code is not None
        and 400 <= status_code < 500
        and status_code not in (409, 422)
    ):
        # Adapter pre-flight rejection (frozen/ceiling/ticket, spec s7 table): NOT_SENT.
        await repo.update_attempt_status(
            session,
            attempt_id=attempt_id,
            new_status=RefundAttemptStatus.NOT_SENT.value,
        )
        outcome20 = await apply_transition(
            session,
            TransitionRequest(
                case_id=case_id,
                expected_from=CaseState.REFUNDING,
                to_state=CaseState.APPROVED,
                expected_version=outcome16.version,
                transition_id="T20",
                actor=Actor.SYSTEM,
                reason_code=None,
            ),
        )
        case_state, attempt_status, execution = (
            outcome20.state.value,
            RefundAttemptStatus.NOT_SENT,
            "QUEUED_FROZEN",
        )
    else:
        # Timeout / 5xx / connection error / unimplemented (501) -> UNKNOWN, reconcile decides.
        await repo.update_attempt_status(
            session, attempt_id=attempt_id, new_status=RefundAttemptStatus.UNKNOWN.value
        )
        await repo.insert_outbox_event(
            session,
            event_id=uuid4(),
            event_type="refund.unknown",
            aggregate_id=str(case_id),
            payload={
                "case_id": str(case_id),
                "order_id": case["order_id"],
                "attempt_id": str(attempt_id),
                "reconcile_count": 0,
            },
        )
        case_state, attempt_status, execution = (
            CaseState.REFUNDING.value,
            RefundAttemptStatus.UNKNOWN,
            "IN_PROGRESS",
        )

    return ExecuteOutcome(
        case_id=case_id,
        case_state=case_state,
        attempt_status=attempt_status,
        execution=execution,
        check_report=report,
    )


async def reconcile_attempts(session: AsyncSession, limit: int) -> ReconcileSummary:
    """Reconcile SENT/UNKNOWN attempts older than the minimum age, oldest first, with SKIP LOCKED.

    Inputs: max rows to examine (api s3.10 `limit`, default 25 at the caller).
    Output: ReconcileSummary counts.
    Edge cases: while frozen, reads (GET refund) still run but replays never send (spec s8, s9);
    repeated UNKNOWN beyond PS_RESOLUTION_RECONCILE_MAX_ATTEMPTS -> needs_review + HUMAN_REVIEW (spec s8 item 3).
    """
    attempts = await repo.get_reconcilable_attempts(
        session, min_age_seconds=settings.refund_min_reconcile_age_s, limit=limit
    )

    examined = 0
    finalized_completed = 0
    finalized_failed = 0
    still_unknown = 0
    needs_review = 0
    frozen_skipped_replays = 0

    flags = await repo.get_control_flags(session)
    frozen = flags is None or flags["refunds_frozen"]

    for attempt in attempts:
        examined += 1
        case = await repo.get_case(session, attempt["case_id"])
        if case is None:
            continue

        if attempt["paypal_refund_id"]:
            result = await clients.get_refund(attempt["paypal_refund_id"])
            body = result.body or {}
            paypal_status = body.get("status")
            if result.status_code == 200 and paypal_status == "COMPLETED":
                await repo.update_attempt_status(
                    session,
                    attempt_id=attempt["id"],
                    new_status=RefundAttemptStatus.COMPLETED.value,
                )
                await apply_transition(
                    session,
                    TransitionRequest(
                        case_id=case["id"],
                        expected_from=CaseState(case["state"]),
                        to_state=CaseState.RESOLVED_REFUNDED,
                        expected_version=case["version"],
                        transition_id="T18",
                        actor=Actor.SYSTEM,
                        reason_code=None,
                    ),
                )
                finalized_completed += 1
                continue
            if result.status_code == 200 and paypal_status in ("FAILED", "CANCELLED"):
                await repo.update_attempt_status(
                    session,
                    attempt_id=attempt["id"],
                    new_status=RefundAttemptStatus.FAILED.value,
                )
                await apply_transition(
                    session,
                    TransitionRequest(
                        case_id=case["id"],
                        expected_from=CaseState(case["state"]),
                        to_state=CaseState.HUMAN_REVIEW,
                        expected_version=case["version"],
                        transition_id="T19",
                        actor=Actor.SYSTEM,
                        reason_code=None,
                    ),
                )
                finalized_failed += 1
                continue
            await repo.update_attempt_status(
                session,
                attempt_id=attempt["id"],
                new_status=attempt["status"],
                bump_reconcile=True,
            )
            still_unknown += 1
        else:
            if frozen:
                # Reads still run; a replay-send never happens while frozen (spec s9).
                frozen_skipped_replays += 1
                continue
            result = await clients.reconcile_refund(attempt["request_id"])
            body = result.body or {}
            if result.status_code in (200, 201) and body.get("status") == "COMPLETED":
                await repo.update_attempt_status(
                    session,
                    attempt_id=attempt["id"],
                    new_status=RefundAttemptStatus.COMPLETED.value,
                    paypal_refund_id=body.get("refund_id") or body.get("id"),
                )
                await apply_transition(
                    session,
                    TransitionRequest(
                        case_id=case["id"],
                        expected_from=CaseState(case["state"]),
                        to_state=CaseState.RESOLVED_REFUNDED,
                        expected_version=case["version"],
                        transition_id="T18",
                        actor=Actor.SYSTEM,
                        reason_code=None,
                    ),
                )
                finalized_completed += 1
                continue
            await repo.update_attempt_status(
                session,
                attempt_id=attempt["id"],
                new_status=RefundAttemptStatus.UNKNOWN.value,
                bump_reconcile=True,
            )
            still_unknown += 1

        if attempt["reconcile_count"] + 1 > settings.reconcile_max_attempts:
            await repo.update_attempt_status(
                session,
                attempt_id=attempt["id"],
                new_status=RefundAttemptStatus.UNKNOWN.value,
            )
            await apply_transition(
                session,
                TransitionRequest(
                    case_id=case["id"],
                    expected_from=CaseState(case["state"]),
                    to_state=CaseState.HUMAN_REVIEW,
                    expected_version=case["version"],
                    transition_id="T19",
                    actor=Actor.SYSTEM,
                    reason_code=None,
                ),
            )
            await repo.insert_outbox_event(
                session,
                event_id=uuid4(),
                event_type="refund.unknown",
                aggregate_id=str(case["id"]),
                payload={
                    "case_id": str(case["id"]),
                    "order_id": case["order_id"],
                    "attempt_id": str(attempt["id"]),
                    "reconcile_count": attempt["reconcile_count"] + 1,
                },
            )
            needs_review += 1

    return ReconcileSummary(
        examined=examined,
        finalized_completed=finalized_completed,
        finalized_failed=finalized_failed,
        still_unknown=still_unknown,
        needs_review=needs_review,
        frozen_skipped_replays=frozen_skipped_replays,
    )
