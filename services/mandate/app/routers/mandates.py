"""Mandate lifecycle endpoints - stubs per mandate/api.md section 4-9.

Wave 4: request validation via the real pydantic schemas (app/schemas/terms.py,
reservations.py); every route returns 501 except health/readyz (conventions doc
section 1). Business logic (canonicalization, HMAC, state derivation, evaluate) is
Wave 5.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.deps import Principal, require_buyer, require_service_caller, verify_internal_jwt
from app.schemas.reservations import EvaluateRequest
from app.schemas.terms import MandatePreviewRequest, MandateSignRequest, RevokeRequest

router = APIRouter(tags=["mandates"])


def _not_implemented(response: Response, path: str) -> dict:
    response.status_code = 501
    return {"error": "not_implemented", "detail": f"{path} pending Wave 5"}


@router.post("/mandates/preview")
async def preview_mandate(
    body: MandatePreviewRequest, response: Response, principal: Principal = Depends(require_buyer)
) -> dict:
    return _not_implemented(response, "POST /mandates/preview")


@router.post("/mandates")
async def sign_mandate(
    body: MandateSignRequest, response: Response, principal: Principal = Depends(require_buyer)
) -> dict:
    return _not_implemented(response, "POST /mandates")


@router.get("/mandates")
async def list_mandates(response: Response, principal: Principal = Depends(require_buyer)) -> dict:
    return _not_implemented(response, "GET /mandates")


@router.get("/mandates/{mandate_id}")
async def get_mandate(
    mandate_id: str, response: Response, principal: Principal = Depends(verify_internal_jwt)
) -> dict:
    return _not_implemented(response, "GET /mandates/{id}")


@router.get("/mandates/{mandate_id}/terms")
async def get_mandate_terms(
    mandate_id: str, response: Response, principal: Principal = Depends(verify_internal_jwt)
) -> dict:
    return _not_implemented(response, "GET /mandates/{id}/terms")


@router.get("/mandates/{mandate_id}/summary")
async def get_mandate_summary(
    mandate_id: str, response: Response, principal: Principal = Depends(require_service_caller)
) -> dict:
    return _not_implemented(response, "GET /mandates/{id}/summary")


@router.get("/mandates/{mandate_id}/verify")
async def verify_mandate(
    mandate_id: str, response: Response, principal: Principal = Depends(verify_internal_jwt)
) -> dict:
    return _not_implemented(response, "GET /mandates/{id}/verify")


@router.post("/mandates/{mandate_id}/revoke")
async def revoke_mandate(
    mandate_id: str, body: RevokeRequest, response: Response, principal: Principal = Depends(require_buyer)
) -> dict:
    return _not_implemented(response, "POST /mandates/{id}/revoke")


@router.post("/mandates/{mandate_id}/evaluate")
async def evaluate_mandate(
    mandate_id: str,
    body: EvaluateRequest,
    response: Response,
    principal: Principal = Depends(require_service_caller),
) -> dict:
    return _not_implemented(response, "POST /mandates/{id}/evaluate")
