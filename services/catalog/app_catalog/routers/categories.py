"""GET /categories, GET /catalog/version - real reads per catalog/api.md."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app_catalog import repo
from app_catalog.deps import Principal, get_session, verify_internal_jwt
from app_catalog.errors import CatalogError
from app_catalog.schemas.items import (
    CatalogVersionResponse,
    CategoriesResponse,
    Category,
)

router = APIRouter(tags=["categories"])


@router.get("/categories", response_model=CategoriesResponse)
async def list_categories(
    principal: Principal = Depends(verify_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> CategoriesResponse:
    rows = await repo.list_categories(session)
    return CategoriesResponse(
        categories=[
            Category(category_id=r.category_id, display_name=r.display_name)
            for r in rows
        ]
    )


@router.get("/catalog/version", response_model=CatalogVersionResponse)
async def catalog_version(
    principal: Principal = Depends(verify_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> CatalogVersionResponse:
    version = await repo.get_latest_version(session)
    if version is None:
        raise CatalogError(503, "NOT_READY", "catalog has no seeded version")
    item_count, merchant_count = await repo.counts_for_version(session, version.version)
    return CatalogVersionResponse(
        catalog_version=version.version,
        seed_hash=version.seed_hash,
        item_count=item_count,
        merchant_count=merchant_count,
    )
