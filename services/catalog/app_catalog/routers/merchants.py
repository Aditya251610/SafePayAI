"""GET /merchants, GET /merchants/{id}/refund-policy-seed - real reads per
catalog/api.md and spec.md section 1 (`v_merchants_public`,
`merchant_refund_policy_seeds`)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app_catalog import repo
from app_catalog.deps import Principal, get_session, verify_internal_jwt
from app_catalog.errors import CatalogError
from app_catalog.schemas.items import (
    Merchant,
    MerchantsResponse,
    RefundPolicySeedResponse,
)

router = APIRouter(tags=["merchants"])


@router.get("/merchants", response_model=MerchantsResponse)
async def list_merchants(
    principal: Principal = Depends(verify_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> MerchantsResponse:
    rows = await repo.list_merchants(session)
    return MerchantsResponse(
        merchants=[
            Merchant(
                merchant_id=r.merchant_id,
                display_name=r.display_name,
                settlement_alias=r.settlement_alias,
                currency=r.currency,
            )
            for r in rows
        ]
    )


@router.get(
    "/merchants/{merchant_id}/refund-policy-seed",
    response_model=RefundPolicySeedResponse,
)
async def refund_policy_seed(
    merchant_id: str,
    principal: Principal = Depends(verify_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> RefundPolicySeedResponse:
    row = await repo.get_refund_policy(session, merchant_id)
    if row is None:
        raise CatalogError(
            404, "MERCHANT_NOT_FOUND", f"merchant {merchant_id!r} not found"
        )
    return RefundPolicySeedResponse(
        merchant_id=row.merchant_id,
        refund_cap_minor=row.refund_cap_minor,
        currency=row.currency,
        excluded_category_ids=row.excluded_category_ids,
        velocity_max_refunds=row.velocity_max_refunds,
        velocity_window_days=row.velocity_window_days,
        authoritative=False,
        note=row.note or "Illustrative seed. Policy engine lives in resolution.",
    )
