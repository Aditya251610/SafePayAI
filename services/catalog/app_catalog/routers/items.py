"""GET /items, GET /items/{sku} - real reads against v_items_public/v_prices_public
joined at the current catalog_version, per catalog/spec.md section 5 and api.md.

Pagination: `limit`/`offset`, capped at 100 per data-architecture.md section 13
("list endpoints paginate, limit <= 100"); a caller-supplied limit above 100 is
clamped rather than rejected (api.md does not document a dedicated error code for
this, and clamping is strictly safer than a hard error for a read-only list route).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app_catalog import repo
from app_catalog.deps import Principal, get_session, verify_internal_jwt
from app_catalog.errors import CatalogError
from app_catalog.schemas.items import Item, ItemDetailResponse, ItemsResponse

router = APIRouter(tags=["items"])

MAX_LIMIT = 100
DEFAULT_LIMIT = 50


def _item_payload(row: repo.ItemRow) -> Item:
    return Item(
        sku=row.sku,
        merchant_id=row.merchant_id,
        category_id=row.category_id,
        title=row.title,
        description=row.description,
        unit_price_minor=row.unit_price_minor,
        currency=row.currency,
        active=row.active,
        text_trust="untrusted",
        label="SIMULATED",
    )


async def _current_version(session: AsyncSession) -> repo.VersionRow:
    version = await repo.get_latest_version(session)
    if version is None:
        raise CatalogError(503, "NOT_READY", "catalog has no seeded version")
    return version


@router.get("/items", response_model=ItemsResponse)
async def list_items(
    merchant_id: str | None = Query(default=None),
    category_id: str | None = Query(default=None),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(verify_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> ItemsResponse:
    version = await _current_version(session)
    capped_limit = min(limit, MAX_LIMIT)
    # Fetch one extra row to compute has_more without a second count query.
    rows = await repo.list_items(
        session,
        version=version.version,
        merchant_id=merchant_id,
        category_id=category_id,
        limit=capped_limit + 1,
        offset=offset,
    )
    has_more = len(rows) > capped_limit
    rows = rows[:capped_limit]
    return ItemsResponse(
        catalog_version=version.version,
        items=[_item_payload(r) for r in rows],
        limit=capped_limit,
        offset=offset,
        has_more=has_more,
    )


@router.get("/items/{sku}", response_model=ItemDetailResponse)
async def get_item(
    sku: str,
    principal: Principal = Depends(verify_internal_jwt),
    session: AsyncSession = Depends(get_session),
) -> ItemDetailResponse:
    version = await _current_version(session)
    row = await repo.get_item(session, sku=sku, version=version.version)
    if row is None:
        raise CatalogError(404, "ITEM_NOT_FOUND", f"item {sku!r} not found")
    payload = _item_payload(row)
    return ItemDetailResponse(**payload.model_dump(), catalog_version=version.version)
