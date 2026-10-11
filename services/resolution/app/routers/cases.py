"""Case endpoints per resolution/api.md sections 3.1-3.9. Wave 4: validated stubs, 501.

The 12-state case machine (spec.md section 3) and the 9 ordered pre-refund checks (section 6)
are Wave 5 business logic; this file only validates request/response shape and wires auth.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import require_idempotency_key, require_internal_jwt
from app.schemas.cases import (
    AppealRequest,
    ApprovalConsentRequest,
    MerchantActionRequest,
    OfferAcceptRequest,
    OfferDeclineRequest,
    ReportCaseRequest,
    ReviewDecisionRequest,
)

router = APIRouter(tags=["cases"])


def _not_implemented(endpoint: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=f"{endpoint} pending Wave 5")


@router.post("/cases/report", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def report_case(
    body: ReportCaseRequest,
    claims: dict = Depends(require_internal_jwt),
    idempotency_key: str = Depends(require_idempotency_key),
) -> None:
    raise _not_implemented("POST /cases/report")


@router.get("/cases/{case_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def get_case(case_id: str, claims: dict = Depends(require_internal_jwt)) -> None:
    raise _not_implemented("GET /cases/{case_id}")


@router.get("/cases", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def list_cases(
    status_: str | None = None,
    order_id: str | None = None,
    claims: dict = Depends(require_internal_jwt),
) -> None:
    raise _not_implemented("GET /cases")


@router.get("/review/queue", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def review_queue(claims: dict = Depends(require_internal_jwt)) -> None:
    raise _not_implemented("GET /review/queue")


@router.post("/cases/{case_id}/review-decision", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def review_decision(
    case_id: str,
    body: ReviewDecisionRequest,
    claims: dict = Depends(require_internal_jwt),
) -> None:
    raise _not_implemented("POST /cases/{case_id}/review-decision")


@router.post("/offers/{offer_id}/accept", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def accept_offer(
    offer_id: str,
    body: OfferAcceptRequest,
    claims: dict = Depends(require_internal_jwt),
) -> None:
    raise _not_implemented("POST /offers/{offer_id}/accept")


@router.post("/offers/{offer_id}/decline", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def decline_offer(
    offer_id: str,
    body: OfferDeclineRequest,
    claims: dict = Depends(require_internal_jwt),
) -> None:
    raise _not_implemented("POST /offers/{offer_id}/decline")


@router.get("/approvals/{token}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def preview_approval(token: str, claims: dict = Depends(require_internal_jwt)) -> None:
    raise _not_implemented("GET /approvals/{token}")


@router.post("/approvals/{token}/consent", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def consent_approval(
    token: str,
    body: ApprovalConsentRequest,
    claims: dict = Depends(require_internal_jwt),
) -> None:
    raise _not_implemented("POST /approvals/{token}/consent")


@router.post("/cases/{case_id}/merchant-action", status_code=status.HTTP_501_NOT_IMPLEMENTED)
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
