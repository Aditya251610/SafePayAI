"""Case endpoints per resolution/api.md sections 3.1-3.9.

All endpoints in this file are real: the buyer-report -> decide -> offer -> accept -> refund
path (report_case, get_case, accept_offer, decline_offer) plus the reviewer/merchant/approval-
link/appeal path (review_decision, merchant_action, appeal_case, preview_approval,
consent_approval, list_cases_route, review_queue) and the notifications read endpoint.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import repo
from app.db import get_session
from app.deps import require_idempotency_key, require_internal_jwt, role_required
from app.domain.policy import Decision, PolicyClass, PolicyConfig, config_from_settings
from app.domain.proposal import Action, ApprovalTier, hashes_match
from app.domain.states import (
    Actor,
    CaseKind,
    CaseOrigin,
    CaseState,
    ConcurrentModification,
    IllegalTransition,
)
from app.schemas.cases import (
    AppealRequest,
    AppealResponse,
    ApprovalConsentRequest,
    ApprovalConsentResponse,
    ApprovalPreviewResponse,
    CaseDetailResponse,
    MerchantActionRequest,
    MerchantActionResponse,
    NotificationsResponse,
    NotificationView,
    OfferAcceptRequest,
    OfferAcceptResponse,
    OfferDeclineRequest,
    OfferDeclineResponse,
    OfferView,
    Reason,
    RefundView,
    ReportCaseRequest,
    ReportCaseResponse,
    ReviewDecisionRequest,
    ReviewDecisionResponse,
    ReviewQueueItem,
    ReviewQueueResponse,
)
from app.settings import settings
from app.usecases.approvals import issue_approval, lookup_approval
from app.usecases.decide import assemble_facts_and_decide
from app.usecases.execute_refund import execute_refund
from app.usecases.offers import accept_offer as uc_accept_offer
from app.usecases.offers import create_offer
from app.usecases.offers import decline_offer as uc_decline_offer
from app.usecases.open_case import OpenCaseCommand
from app.usecases.open_case import open_case as uc_open_case
from app.usecases.review import decide_with_override
from app.usecases.transitions import TransitionRequest, apply_transition

router = APIRouter(tags=["cases"])


def _not_implemented(endpoint: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=f"{endpoint} pending Wave 5"
    )


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


async def decide_and_offer(
    session: AsyncSession, case_id: UUID
) -> tuple[Decision, OfferView | None]:
    """Shared decide -> offer-creation step (api.md s3.1, s3.2 OFFERED path), used by both
    POST /cases/report (BUYER_REPORT) and the DETECTOR-origin inbox handler
    (routers/internal.py) so a late/lost detection reaches the same automated offer path
    without needing triage-ai at all (spec s3 T5: detector origin skips triage)."""
    decision = await assemble_facts_and_decide(session, case_id, _policy_config())

    offer_view: OfferView | None = None
    if decision.klass in (PolicyClass.INSIDE_TERMS, PolicyClass.OUTSIDE_TERMS):
        tier = (
            ApprovalTier.CONFIRM
            if decision.klass == PolicyClass.INSIDE_TERMS
            else ApprovalTier.APPROVE
        )
        offer = await create_offer(session, case_id, decision, Action.REFUND, tier)
        offer_view = OfferView(
            offer_id=str(offer.offer_id),
            action=offer.action.value,
            amount_minor=offer.amount_minor,
            currency=offer.currency,
            tier=offer.tier.value,
            status=offer.status.value,
            proposal_hash=offer.proposal_hash,
            expires_at="",
        )
    return decision, offer_view


@router.post("/cases/report", status_code=201)
async def report_case(
    body: ReportCaseRequest,
    claims: dict = Depends(require_internal_jwt),
    idempotency_key: str = Depends(require_idempotency_key),
    session: AsyncSession = Depends(get_session),
) -> ReportCaseResponse:
    opened = await uc_open_case(
        session,
        OpenCaseCommand(
            order_id=UUID(body.order_id),
            # Intentional OPEN-TIME PLACEHOLDER, not a dead end: decide_and_offer below runs
            # triage-ai synchronously in this same request and reclassifies case.kind from
            # triage's real `category` before the first policy decision is made (see
            # app/usecases/decide.py's "Reclassify case.kind" block). A case can only ever be
            # opened with a kind that's already certain (DETECTOR) or not yet known
            # (BUYER_REPORT) -- OTHER is the only honest value here until triage answers.
            kind=CaseKind.OTHER,
            origin=CaseOrigin.BUYER_REPORT,
            source_event_id=None,
            untrusted_text=body.text[: settings.case_report_max_chars],
        ),
    )
    decision, offer_view = await decide_and_offer(session, opened.case_id)
    await session.commit()

    case = await repo.get_case(session, opened.case_id)
    return ReportCaseResponse(
        case_id=str(opened.case_id),
        state=case["state"] if case else opened.state.value,
        # Reflects decide_and_offer's triage reclassification above, not the OTHER placeholder
        # the case was opened with -- this was the original bug (hardcoded "OTHER" literal).
        kind=case["kind"] if case else "OTHER",
        origin="BUYER_REPORT",
        reasons=[Reason(code=r.code.value) for r in decision.reasons],
        offer=offer_view,
        protection={},
    )


@router.get("/cases/{case_id}")
async def get_case_route(
    case_id: str,
    claims: dict = Depends(require_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> CaseDetailResponse:
    case = await repo.get_case(session, UUID(case_id))
    if case is None:
        raise HTTPException(status_code=404, detail="CASE_NOT_FOUND")
    # IDOR guard: a buyer may only read their own case -- matches list_cases_route's own
    # buyer_id scoping. 404, not 403, so existence of another buyer's case isn't leaked.
    role = (claims.get("act") or {}).get("role")
    if role == "buyer" and str(case["buyer_id"]) != str(claims.get("buyer_id")):
        raise HTTPException(status_code=404, detail="CASE_NOT_FOUND")
    return CaseDetailResponse(
        case_id=str(case["id"]),
        order_id=case["order_id"],
        state=case["state"],
        version=case["version"],
        kind=case["kind"],
        origin=case["origin"],
        opened_at=case["opened_at"].isoformat(),
        window_hold=case["window_hold"],
    )


@router.get("/cases")
async def list_cases_route(
    status_: str | None = None,
    order_id: str | None = None,
    claims: dict = Depends(require_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> dict:
    role = (claims.get("act") or {}).get("role")
    buyer_id = str(claims.get("buyer_id")) if role == "buyer" else None
    rows = await repo.list_cases(
        session, status=status_, order_id=order_id, buyer_id=buyer_id
    )
    return {
        "items": [
            {
                "case_id": str(r["id"]),
                "order_id": r["order_id"],
                "state": r["state"],
                "kind": r["kind"],
                "origin": r["origin"],
                "opened_at": r["opened_at"].isoformat(),
            }
            for r in rows
        ]
    }


@router.get("/review/queue")
async def review_queue(
    claims: dict = Depends(role_required("reviewer")),
    session: AsyncSession = Depends(get_session),
) -> ReviewQueueResponse:
    rows = await repo.get_review_queue(session)
    now = repo.now_utc()
    target = settings.human_review_sla_target_s
    items = []
    for r in rows:
        entered_at = r.get("human_review_entered_at") or r["opened_at"]
        age_s = int((now - entered_at).total_seconds())
        sla_state: Literal["NO_TARGET", "WITHIN", "OVER"] = (
            "NO_TARGET" if target is None else ("OVER" if age_s > target else "WITHIN")
        )
        reason = r.get("human_review_reason")
        items.append(
            ReviewQueueItem(
                case_id=str(r["id"]),
                kind=r["kind"],
                reason_codes=[reason] if reason else [],
                entered_at=entered_at.isoformat(),
                age_s=age_s,
                sla_target_s=target,
                sla_state=sla_state,
                brief=reason or "Case requires human review.",
            )
        )
    return ReviewQueueResponse(items=items)


@router.post("/cases/{case_id}/review-decision")
async def review_decision(
    case_id: str,
    body: ReviewDecisionRequest,
    claims: dict = Depends(role_required("reviewer")),
    session: AsyncSession = Depends(get_session),
) -> ReviewDecisionResponse:
    """api.md s3.4: the only way a HUMAN_REVIEW case ever leaves that state. PROPOSE_REFUND/
    PROPOSE_RESHIP implement T13 (always tier APPROVE: an exception path needing buyer consent
    via approval link, not an instant auto-accept -- deliberate, not agonized over). DECLINE/
    CLOSE implement T14/T15 and require a written reason (422 REASON_REQUIRED)."""
    cid = UUID(case_id)
    case = await repo.get_case_for_update(session, cid)
    if case is None:
        raise HTTPException(status_code=404, detail="CASE_NOT_FOUND")
    if CaseState(case["state"]) != CaseState.HUMAN_REVIEW:
        raise HTTPException(status_code=409, detail="ILLEGAL_TRANSITION")

    if body.decision in ("DECLINE", "CLOSE") and not (
        body.reason and body.reason.strip()
    ):
        raise HTTPException(status_code=422, detail="REASON_REQUIRED")

    # Auditable record of who decided and why. case_transitions.reason is typed to the
    # ReasonCode enum via apply_transition (not free text), so reviewer_name/reason go to
    # case_signals instead -- never lost, just not forced into the wrong column.
    await repo.insert_case_signal(
        session,
        case_id=cid,
        kind="review_decision",
        payload={
            "decision": body.decision,
            "reviewer_name": body.reviewer_name,
            "reason": body.reason,
        },
    )

    offer_id: str | None = None
    try:
        if body.decision in ("PROPOSE_REFUND", "PROPOSE_RESHIP"):
            action = (
                Action.REFUND if body.decision == "PROPOSE_REFUND" else Action.RESHIP
            )
            decision = await decide_with_override(session, cid, _policy_config())
            offer = await create_offer(
                session, cid, decision, action, ApprovalTier.APPROVE
            )
            token = await issue_approval(session, offer)
            await repo.insert_notification(
                session,
                case_id=cid,
                buyer_id=case.get("buyer_id"),
                type="APPROVAL_LINK",
                body=f"{settings.approval_base_url}/approvals/{token}",
            )
            offer_id = str(offer.offer_id)
            outcome = await apply_transition(
                session,
                TransitionRequest(
                    case_id=cid,
                    expected_from=CaseState.HUMAN_REVIEW,
                    to_state=CaseState.OFFERED,
                    expected_version=case["version"],
                    transition_id="T13",
                    actor=Actor.REVIEWER,
                    reason_code=None,
                ),
            )
        elif body.decision == "DECLINE":
            outcome = await apply_transition(
                session,
                TransitionRequest(
                    case_id=cid,
                    expected_from=CaseState.HUMAN_REVIEW,
                    to_state=CaseState.DECLINED,
                    expected_version=case["version"],
                    transition_id="T14",
                    actor=Actor.REVIEWER,
                    reason_code=None,
                ),
            )
        else:  # CLOSE
            outcome = await apply_transition(
                session,
                TransitionRequest(
                    case_id=cid,
                    expected_from=CaseState.HUMAN_REVIEW,
                    to_state=CaseState.CLOSED,
                    expected_version=case["version"],
                    transition_id="T15",
                    actor=Actor.REVIEWER,
                    reason_code=None,
                ),
            )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (IllegalTransition, ConcurrentModification) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await session.commit()
    return ReviewDecisionResponse(
        case_id=case_id, state=outcome.state.value, offer_id=offer_id
    )


@router.post("/offers/{offer_id}/accept")
async def accept_offer_route(
    offer_id: str,
    body: OfferAcceptRequest,
    claims: dict = Depends(require_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> OfferAcceptResponse:
    buyer_id = str(claims.get("sub", ""))
    try:
        result = await uc_accept_offer(
            session, UUID(offer_id), buyer_id, body.proposal_hash
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="OFFER_NOT_FOUND") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()

    execution = "NOT_STARTED"
    refund_status = "NONE"
    if not result.replayed and result.state == "APPROVED":
        outcome = await execute_refund(session, result.case_id)
        execution = outcome.execution
        refund_status = (
            outcome.attempt_status.value if outcome.attempt_status else "NONE"
        )
        await session.commit()
        case_state = outcome.case_state
    else:
        case_state = result.state

    return OfferAcceptResponse(
        case_id=str(result.case_id),
        state=case_state,  # type: ignore[arg-type]
        execution=execution,  # type: ignore[arg-type]
        refund=RefundView(status=refund_status, paypal_refund_id=None),  # type: ignore[arg-type]
    )


@router.post("/offers/{offer_id}/decline")
async def decline_offer_route(
    offer_id: str,
    body: OfferDeclineRequest,
    claims: dict = Depends(require_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> OfferDeclineResponse:
    buyer_id = str(claims.get("sub", ""))
    try:
        await uc_decline_offer(session, UUID(offer_id), buyer_id, body.reason_code)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="OFFER_NOT_FOUND") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    return OfferDeclineResponse(state="DECLINED")


@router.get("/approvals/{token}")
async def preview_approval(
    token: str,
    claims: dict = Depends(require_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> ApprovalPreviewResponse:
    """api.md s3.7: pure read, no state change. 404 for any invalid/expired/revoked/consumed
    token (no enumeration of which)."""
    looked_up = await lookup_approval(session, token)
    if looked_up is None:
        raise HTTPException(status_code=404, detail="APPROVAL_NOT_FOUND")
    if looked_up.status == "consumed":
        raise HTTPException(status_code=404, detail="APPROVAL_REPLAY")
    if looked_up.status == "revoked":
        raise HTTPException(status_code=404, detail="APPROVAL_REVOKED")
    if looked_up.expires_at is not None and looked_up.expires_at < repo.now_utc():
        raise HTTPException(status_code=404, detail="APPROVAL_EXPIRED")

    offer = await repo.get_offer(session, looked_up.proposal_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="APPROVAL_NOT_FOUND")
    case = await repo.get_case(session, offer["case_id"])
    if case is None:
        raise HTTPException(status_code=404, detail="APPROVAL_NOT_FOUND")

    summary = (
        f"Approve a {offer['action'].lower()} of "
        f"{offer['amount_minor'] / 100:.2f} {offer['currency']} for this order?"
    )
    return ApprovalPreviewResponse(
        case_id=str(case["id"]),
        action=offer["action"],
        amount_minor=offer["amount_minor"],
        currency=offer["currency"],
        summary=summary,
        expires_at=looked_up.expires_at.isoformat() if looked_up.expires_at else "",
        proposal_hash=offer["proposal_hash"],
    )


@router.post("/approvals/{token}/consent")
async def consent_approval(
    token: str,
    body: ApprovalConsentRequest,
    claims: dict = Depends(require_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> ApprovalConsentResponse:
    """api.md s3.7: the buyer's tier-2 consent. Mirrors accept_offer_route (same T9, same
    execute_refund call) -- the only difference is how the offer gets authorized (single-use
    link token + proposal_hash, not a `sub`-owned offer id)."""
    looked_up = await lookup_approval(session, token)
    if looked_up is None:
        raise HTTPException(status_code=404, detail="APPROVAL_NOT_FOUND")
    if looked_up.status == "consumed":
        raise HTTPException(status_code=409, detail="APPROVAL_REPLAY")
    if looked_up.status == "revoked":
        raise HTTPException(status_code=404, detail="APPROVAL_REVOKED")
    if looked_up.expires_at is not None and looked_up.expires_at < repo.now_utc():
        raise HTTPException(status_code=404, detail="APPROVAL_EXPIRED")
    if not hashes_match(looked_up.proposal_hash, body.proposal_hash):
        raise HTTPException(status_code=409, detail="PROPOSAL_HASH_MISMATCH")

    offer = await repo.get_offer(session, looked_up.proposal_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="APPROVAL_NOT_FOUND")
    case = await repo.get_case_for_update(session, offer["case_id"])
    if case is None:
        raise HTTPException(status_code=404, detail="APPROVAL_NOT_FOUND")
    # Defense in depth: the token itself is the primary bearer-credential (single-use,
    # time-limited, unguessable -- lookup_approval's own docstring), but a caller
    # authenticated AS a specific buyer should never be able to consent on a DIFFERENT
    # buyer's case even if they somehow obtained that buyer's token (e.g. the
    # notifications.body leak this same pass fixed in get_notifications). Non-buyer
    # callers (a merchant/service relaying on the real buyer's behalf) are unaffected --
    # same convention as get_case_route/list_notifications in this file.
    role = (claims.get("act") or {}).get("role")
    if role == "buyer" and str(case["buyer_id"]) != str(claims.get("sub", "")):
        raise HTTPException(status_code=404, detail="APPROVAL_NOT_FOUND")

    consumed = await repo.consume_approval(session, looked_up.approval_id)
    if not consumed:
        # Lost a race against another consent for the same link, or already consumed.
        raise HTTPException(status_code=409, detail="APPROVAL_REPLAY")

    if offer["status"] == "ACCEPTED":
        # Replayed: the offer itself was already accepted (e.g. by a concurrent consent that
        # won the accept race right after we won the consume race). Same case, existing state.
        await session.commit()
        return ApprovalConsentResponse(
            case_id=str(case["id"]), state=case["state"], execution="DONE"
        )
    if offer["status"] != "ACTIVE":
        raise HTTPException(status_code=409, detail="OFFER_NOT_ACTIVE")

    won = await repo.cas_accept_offer(session, offer["id"])
    if not won:
        refreshed = await repo.get_offer(session, offer["id"])
        if refreshed and refreshed["status"] == "ACCEPTED":
            await session.commit()
            return ApprovalConsentResponse(
                case_id=str(case["id"]), state=case["state"], execution="DONE"
            )
        raise HTTPException(status_code=409, detail="OFFER_NOT_ACTIVE")

    if offer["action"] == Action.RESHIP.value:
        # Same guard as usecases.offers.accept_offer: a RESHIP offer's consent only marks
        # it ACCEPTED (cas_accept_offer above) -- the case stays wherever it is until
        # POST /cases/{id}/merchant-action CONFIRM_RESHIP drives T10. Never T9/APPROVED for
        # a RESHIP offer, since APPROVED is "ready for execute_refund" and a reship must
        # never trigger a real refund. (Found live: a fresh RESHIP offer accepted through
        # this exact path incorrectly executed a real PayPal refund before this fix.)
        await session.commit()
        return ApprovalConsentResponse(
            case_id=str(case["id"]), state=case["state"], execution="DONE"
        )

    try:
        await apply_transition(
            session,
            TransitionRequest(
                case_id=case["id"],
                expected_from=CaseState(case["state"]),
                to_state=CaseState.APPROVED,
                expected_version=case["version"],
                transition_id="T9",
                actor=Actor.BUYER,
                reason_code=None,
            ),
        )
    except (IllegalTransition, ConcurrentModification) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()

    outcome = await execute_refund(session, case["id"])
    await session.commit()
    return ApprovalConsentResponse(
        case_id=str(case["id"]),
        state=outcome.case_state,  # type: ignore[arg-type]
        execution=outcome.execution,  # type: ignore[arg-type]
    )


@router.post("/cases/{case_id}/merchant-action")
async def merchant_action(
    case_id: str,
    body: MerchantActionRequest,
    claims: dict = Depends(role_required("merchant")),
    session: AsyncSession = Depends(get_session),
) -> MerchantActionResponse:
    """api.md s3.8. No amount is accepted from the client (server-computed only, money-path).
    OVERRIDE_OFFER implements T25 (from DECLINED) or T26 (from OFFERED, self-loop supersede),
    always tier APPROVE (merchant can propose, buyer must still consent -- T25/T26 guard).
    CONFIRM_RESHIP implements T10."""
    cid = UUID(case_id)
    case = await repo.get_case_for_update(session, cid)
    if case is None:
        raise HTTPException(status_code=404, detail="CASE_NOT_FOUND")
    state = CaseState(case["state"])

    await repo.insert_case_signal(
        session,
        case_id=cid,
        kind="merchant_shared",
        payload={"type": body.type, "state": state.value},
    )

    if body.type == "OVERRIDE_OFFER":
        if state not in (CaseState.DECLINED, CaseState.OFFERED):
            raise HTTPException(status_code=409, detail="ILLEGAL_TRANSITION")
        old_offer = await repo.get_latest_offer_for_case(session, cid)
        transition_id = "T26" if state == CaseState.OFFERED else "T25"
        try:
            decision = await decide_with_override(session, cid, _policy_config())
            new_offer = await create_offer(
                session, cid, decision, Action.REFUND, ApprovalTier.APPROVE
            )
            if old_offer is not None:
                await repo.supersede_active_offers(session, cid, new_offer.offer_id)
                await repo.revoke_approvals_for_proposal(session, old_offer["id"])
            token = await issue_approval(session, new_offer)
            await repo.insert_notification(
                session,
                case_id=cid,
                buyer_id=case.get("buyer_id"),
                type="APPROVAL_LINK",
                body=f"{settings.approval_base_url}/approvals/{token}",
            )
            outcome = await apply_transition(
                session,
                TransitionRequest(
                    case_id=cid,
                    expected_from=state,
                    to_state=CaseState.OFFERED,
                    expected_version=case["version"],
                    transition_id=transition_id,
                    actor=Actor.MERCHANT,
                    reason_code=None,
                ),
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (IllegalTransition, ConcurrentModification) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        await session.commit()
        return MerchantActionResponse(
            case_id=case_id,
            state=outcome.state.value,
            offer_id=str(new_offer.offer_id),
            supersedes=str(old_offer["id"]) if old_offer else None,
        )

    # CONFIRM_RESHIP (T10): legal only while the case still holds an active/accepted RESHIP
    # offer and is still OFFERED.
    #
    # Flagged for the integrator (out of this task's file scope, not silently worked around):
    # usecases/offers.py's accept_offer() always drives T9 (OFFERED -> APPROVED) regardless of
    # the offer's action, so a buyer "accepting" a RESHIP-action offer today leaves the case
    # APPROVED, not OFFERED -- and this branch, written faithfully against states.py's T10
    # (OFFERED -> RESOLVED_RESHIP), can never legally fire for that path yet. offers.py wasn't
    # in this task's edit list, so I did not change its branching on Action there; a follow-up
    # should make accept_offer() leave RESHIP-action offers ACCEPTED-but-case-stays-OFFERED
    # instead of always transitioning to APPROVED.
    if state != CaseState.OFFERED:
        raise HTTPException(status_code=409, detail="ILLEGAL_TRANSITION")
    offer = await repo.get_latest_offer_for_case(session, cid)
    if (
        offer is None
        or offer["action"] != "RESHIP"
        or offer["status"] not in ("ACTIVE", "ACCEPTED")
    ):
        raise HTTPException(status_code=409, detail="ILLEGAL_TRANSITION")
    try:
        outcome = await apply_transition(
            session,
            TransitionRequest(
                case_id=cid,
                expected_from=CaseState.OFFERED,
                to_state=CaseState.RESOLVED_RESHIP,
                expected_version=case["version"],
                transition_id="T10",
                actor=Actor.MERCHANT,
                reason_code=None,
            ),
        )
    except (IllegalTransition, ConcurrentModification) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    return MerchantActionResponse(
        case_id=case_id,
        state=outcome.state.value,
        offer_id=str(offer["id"]),
        supersedes=None,
    )


@router.post("/cases/{case_id}/appeal")
async def appeal_case(
    case_id: str,
    body: AppealRequest,
    claims: dict = Depends(require_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> AppealResponse:
    """api.md s3.9: implements T24 (DECLINED -> HUMAN_REVIEW). Ownership check mirrors
    accept_offer_route/decline_offer_route (buyer id from the bare `sub` claim, per this
    service's existing convention -- see .claude/memory/entries/internal-auth-convention-chaos.md);
    wrong owner -> 404, no enumeration."""
    buyer_id = str(claims.get("sub", ""))
    cid = UUID(case_id)
    case = await repo.get_case_for_update(session, cid)
    if case is None or case.get("buyer_id") != buyer_id:
        raise HTTPException(status_code=404, detail="CASE_NOT_FOUND")
    # T24 is specifically DECLINED -> HUMAN_REVIEW ("buyer appeals a declined case"),
    # but apply_transition's is_legal_transition only checks the (from, to) STATE pair,
    # not which transition_id is allowed to produce it -- REFUNDING -> HUMAN_REVIEW is
    # ALSO a legal pair (a different, system-initiated escalation), so without this
    # explicit check a buyer could call appeal while their case is mid-refund and push
    # it into HUMAN_REVIEW while the refund still completes at PayPal.
    if CaseState(case["state"]) != CaseState.DECLINED:
        raise HTTPException(status_code=409, detail="ILLEGAL_TRANSITION")

    if body.note:
        await repo.insert_case_signal(
            session,
            case_id=cid,
            kind="appeal_note",
            payload={"note": body.note[: settings.case_report_max_chars]},
        )

    try:
        await apply_transition(
            session,
            TransitionRequest(
                case_id=cid,
                expected_from=CaseState(case["state"]),
                to_state=CaseState.HUMAN_REVIEW,
                expected_version=case["version"],
                transition_id="T24",
                actor=Actor.BUYER,
                reason_code=None,
            ),
        )
    except (IllegalTransition, ConcurrentModification) as exc:
        raise HTTPException(status_code=409, detail="ILLEGAL_TRANSITION") from exc
    await session.commit()
    return AppealResponse(state="HUMAN_REVIEW")


@router.get("/notifications")
async def list_notifications(
    claims: dict = Depends(require_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> NotificationsResponse:
    """api.md section 2: "B(own), M" -- a buyer sees only their own notifications, a
    merchant sees all. Same claims convention as list_cases_route in this file (verified
    against app/deps.py's require_internal_jwt: claims.act.role / claims.buyer_id)."""
    role = (claims.get("act") or {}).get("role")
    buyer_id = str(claims.get("buyer_id")) if role == "buyer" else None
    rows = await repo.get_notifications(session, buyer_id=buyer_id)
    return NotificationsResponse(
        items=[
            NotificationView(
                id=str(r["id"]),
                case_id=str(r["case_id"]),
                type=r["type"],
                created_at=r["created_at"].isoformat(),
                body=r["body"],
            )
            for r in rows
        ]
    )
