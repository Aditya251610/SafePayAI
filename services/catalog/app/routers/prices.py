"""POST /prices/resolve - server-authoritative pricing, catalog/spec.md section 3 and 5.

Hard rules enforced here (never relaxed):
- The only price source is the DB (`item_prices` via `v_prices_public`); nothing from
  the request body ever becomes `unit_price_minor`/`line_total_minor`/`total_minor`.
- All money math is `int * int = int`; no float appears anywhere in this module.
- Errors never partial: unknown SKUs / inactive SKUs are collected across the whole
  request and reported together before any pricing is computed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app import repo
from app.deps import Principal, get_session, verify_internal_jwt
from app.errors import CatalogError
from app.schemas.prices import PricedLine, PriceResolveRequest, PriceResolveResponse
from app.settings import Settings, get_settings

router = APIRouter(tags=["prices"])


@router.post("/prices/resolve", response_model=PriceResolveResponse)
async def resolve_prices(
    body: PriceResolveRequest,
    principal: Principal = Depends(verify_internal_jwt),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> PriceResolveResponse:
    # 1. EMPTY_CART
    if not body.lines:
        raise CatalogError(422, "EMPTY_CART", "lines must contain at least one entry")

    # 2. line-count technical bound (PS_CATALOG_MAX_LINES)
    if len(body.lines) > settings.max_lines:
        raise CatalogError(
            422,
            "VALIDATION_ERROR",
            f"too many lines: {len(body.lines)} > PS_CATALOG_MAX_LINES={settings.max_lines}",
            {"max_lines": settings.max_lines, "received": len(body.lines)},
        )

    # 3. DUPLICATE_SKU_LINE
    seen: set[str] = set()
    duplicates: set[str] = set()
    for line in body.lines:
        if line.sku in seen:
            duplicates.add(line.sku)
        seen.add(line.sku)
    if duplicates:
        raise CatalogError(
            422,
            "DUPLICATE_SKU_LINE",
            "each SKU may appear at most once per request",
            {"skus": sorted(duplicates)},
        )

    # 4. INVALID_QUANTITY (not int-typed is already rejected at the pydantic layer)
    bad_qty = [
        {"sku": line.sku, "qty": line.qty}
        for line in body.lines
        if not (1 <= line.qty <= settings.max_line_qty)
    ]
    if bad_qty:
        raise CatalogError(
            422,
            "INVALID_QUANTITY",
            f"qty must be between 1 and {settings.max_line_qty}",
            {"lines": bad_qty, "max_line_qty": settings.max_line_qty},
        )

    # 5. CURRENCY_MISMATCH
    if body.currency is not None and body.currency != "USD":
        raise CatalogError(
            422,
            "CURRENCY_MISMATCH",
            "catalog only prices in USD",
            {"requested_currency": body.currency},
        )

    # 6. catalog_version pinning
    latest = await repo.get_latest_version(session)
    if latest is None:
        raise CatalogError(503, "NOT_READY", "catalog has no seeded version")

    if body.catalog_version is not None:
        pinned = await repo.get_version(session, body.catalog_version)
        if pinned is None:
            raise CatalogError(
                404,
                "CATALOG_VERSION_UNKNOWN",
                f"catalog_version {body.catalog_version} not found",
            )
        resolve_version = pinned.version
    else:
        resolve_version = latest.version

    # 7. one query for every requested SKU at the resolved version
    skus = [line.sku for line in body.lines]
    found = await repo.list_items_for_resolve(
        session, skus=skus, version=resolve_version
    )

    unknown = [sku for sku in skus if sku not in found]
    if unknown:
        raise CatalogError(
            422,
            "UNKNOWN_SKU",
            "One or more SKUs are not in the catalog",
            {"skus": unknown},
        )

    # 8. ITEM_INACTIVE (only matters when resolving the current/latest version; an
    # item deactivated later still prices fine under an older pinned version where it
    # was active - spec.md section 4).
    inactive = [sku for sku in skus if not found[sku].active]
    if inactive:
        raise CatalogError(
            422,
            "ITEM_INACTIVE",
            "One or more SKUs are inactive in this version",
            {"skus": inactive},
        )

    # 9. latest_unit_price_minor diffs, only queried when pinned != latest.
    latest_prices: dict[str, int] = {}
    if resolve_version != latest.version:
        latest_prices = await repo.latest_prices_for_skus(
            session, skus=skus, version=latest.version
        )

    merchants = {m.merchant_id: m for m in await repo.list_merchants(session)}

    priced_lines: list[PricedLine] = []
    merchant_ids: set[str] = set()
    total_minor = 0
    price_mismatch_any = False

    for line in body.lines:
        item = found[line.sku]
        unit_price_minor = item.unit_price_minor
        line_total_minor = unit_price_minor * line.qty  # int * int, never float
        total_minor += line_total_minor
        merchant_ids.add(item.merchant_id)

        price_mismatch = False
        if line.agent_stated_price_minor is not None:
            price_mismatch = line.agent_stated_price_minor != unit_price_minor
            price_mismatch_any = price_mismatch_any or price_mismatch

        latest_unit_price_minor = latest_prices.get(line.sku)
        if (
            latest_unit_price_minor is not None
            and latest_unit_price_minor == unit_price_minor
        ):
            latest_unit_price_minor = (
                None  # only reported when it differs (spec.md section 4)
            )

        merchant = merchants.get(item.merchant_id)
        if (
            merchant is None
        ):  # pragma: no cover - defensive; items always have a valid FK
            raise CatalogError(
                404, "MERCHANT_NOT_FOUND", f"merchant {item.merchant_id!r} not found"
            )

        priced_lines.append(
            PricedLine(
                sku=line.sku,
                title=item.title,
                merchant_id=item.merchant_id,
                category_id=item.category_id,
                qty=line.qty,
                unit_price_minor=unit_price_minor,
                line_total_minor=line_total_minor,
                settlement_alias=merchant.settlement_alias,
                price_mismatch=price_mismatch,
                latest_unit_price_minor=latest_unit_price_minor,
            )
        )

    return PriceResolveResponse(
        catalog_version=resolve_version,
        currency="USD",
        lines=priced_lines,
        merchant_ids=sorted(merchant_ids),
        total_minor=total_minor,
        price_mismatch_any=price_mismatch_any,
    )
