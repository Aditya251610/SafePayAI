"""Spend reservation endpoints (service callers only) - stubs per mandate/api.md section 10-11."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.deps import Principal, require_service_caller
from app.schemas.reservations import (
    AuthorizeCaptureRequest,
    CommitRequest,
    MarkUnknownRequest,
    ReleaseRequest,
    ReservationCreateRequest,
)

router = APIRouter(tags=["reservations"])


def _not_implemented(response: Response, path: str) -> dict:
    response.status_code = 501
    return {"error": "not_implemented", "detail": f"{path} pending Wave 5"}


@router.post("/mandates/{mandate_id}/reservations")
async def create_reservation(
    mandate_id: str,
    body: ReservationCreateRequest,
    response: Response,
    principal: Principal = Depends(require_service_caller),
) -> dict:
    return _not_implemented(response, "POST /mandates/{id}/reservations")


@router.get("/reservations/{reservation_id}")
async def get_reservation(
    reservation_id: str, response: Response, principal: Principal = Depends(require_service_caller)
) -> dict:
    return _not_implemented(response, "GET /reservations/{id}")


@router.post("/reservations/{reservation_id}/authorize-capture")
async def authorize_capture(
    reservation_id: str,
    body: AuthorizeCaptureRequest,
    response: Response,
    principal: Principal = Depends(require_service_caller),
) -> dict:
    return _not_implemented(response, "POST /reservations/{id}/authorize-capture")


@router.post("/reservations/{reservation_id}/mark-unknown")
async def mark_unknown(
    reservation_id: str,
    body: MarkUnknownRequest,
    response: Response,
    principal: Principal = Depends(require_service_caller),
) -> dict:
    return _not_implemented(response, "POST /reservations/{id}/mark-unknown")


@router.post("/reservations/{reservation_id}/commit")
async def commit_reservation(
    reservation_id: str,
    body: CommitRequest,
    response: Response,
    principal: Principal = Depends(require_service_caller),
) -> dict:
    return _not_implemented(response, "POST /reservations/{id}/commit")


@router.post("/reservations/{reservation_id}/release")
async def release_reservation(
    reservation_id: str,
    body: ReleaseRequest,
    response: Response,
    principal: Principal = Depends(require_service_caller),
) -> dict:
    return _not_implemented(response, "POST /reservations/{id}/release")
