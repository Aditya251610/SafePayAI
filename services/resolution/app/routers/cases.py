"""Case endpoints per resolution/api.md sections 3.1-3.9.

Wired (Wave 5B) for the buyer-report -> decide -> offer -> accept -> refund path: report_case,
get_case, accept_offer, decline_offer. Reviewer/merchant/approval-link paths (review_decision,
merchant_action, appeal_case, approvals preview/consent, list_cases, review_queue,
notifications) stay 501: they need the `approvals` table and reviewer tooling this wave did not
scaffold usecases for (resolution/app/usecases only covers open_case/decide/offers/execute_refund).
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import repo
from app.db import get_session
from app.deps import require_idempotency_key, require_internal_jwt
from app.domain.policy import Decision, PolicyClass, PolicyConfig, config_from_settings
from app.domain.proposal import Action, ApprovalTier
from app.domain.states import CaseKind, CaseOrigin
from app.schemas.cases import (
    AppealRequest,
    ApprovalConsentRequest,
    CaseDetailResponse,
    MerchantActionRequest,
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
    ReviewQueueItem,
    ReviewQueueResponse,
)
from app.settings import settings
from app.usecases.decide import assemble_facts_and_decide
from app.usecases.execute_refund import execute_refund
from app.usecases.offers import accept_offer as uc_accept_offer
from app.usecases.offers import create_offer
from app.usecases.offers import decline_offer as uc_decline_offer
from app.usecases.open_case import OpenCaseCommand
from app.usecases.open_case import open_case as uc_open_case

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
        kind="OTHER",
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
    claims: dict = Depends(require_internal_jwt),
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


@router.post(
    "/cases/{case_id}/review-decision", status_code=status.HTTP_501_NOT_IMPLEMENTED
)
async def review_decision(
    case_id: str,
    body: ReviewDecisionRequest,
    claims: dict = Depends(require_internal_jwt),
) -> None:
    raise _not_implemented("POST /cases/{case_id}/review-decision")


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


@router.get("/approvals/{token}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def preview_approval(
    token: str, claims: dict = Depends(require_internal_jwt)
) -> None:
    raise _not_implemented("GET /approvals/{token}")


@router.post("/approvals/{token}/consent", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def consent_approval(
    token: str,
    body: ApprovalConsentRequest,
    claims: dict = Depends(require_internal_jwt),
) -> None:
    raise _not_implemented("POST /approvals/{token}/consent")


@router.post(
    "/cases/{case_id}/merchant-action", status_code=status.HTTP_501_NOT_IMPLEMENTED
)
async def merchant_action(
    case_id: str,
    body: MerchantActionRequest,
    claims: dict = Depends(require_internal_jwt),
) -> None:
    raise _not_implemented("POST /cases/{case_id}/merchant-action")


@router.post("/cases/{case_id}/appeal", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def appeal_case(
    case_id: str,
    body: AppealRequest,
    claims: dict = Depends(require_internal_jwt),
) -> None:
    raise _not_implemented("POST /cases/{case_id}/appeal")


@router.get("/notifications", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def list_notifications(claims: dict = Depends(require_internal_jwt)) -> None:
    raise _not_implemented("GET /notifications")
