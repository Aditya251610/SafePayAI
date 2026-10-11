"""Read-only DB access for catalog, against the public views / reference tables the
runtime role `svc_catalog` is granted (migrations 0001, 0003). No ORM models - the
schema is tiny and hand-written SQL keeps the "SELECT * never used, queries are the
documented read path" property auditable (data-architecture.md section 13).

All money fields come back as Python `int` (Postgres bigint -> int via asyncpg); no
float conversion happens anywhere in this module.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

SCHEMA = "catalog"


@dataclass(frozen=True)
class VersionRow:
    version: int
    seed_hash: str


@dataclass(frozen=True)
class ItemRow:
    sku: str
    merchant_id: str
    category_id: str
    title: str
    description: str
    active: bool
    unit_price_minor: int
    currency: str


@dataclass(frozen=True)
class MerchantRow:
    merchant_id: str
    display_name: str
    settlement_alias: str
    currency: str


@dataclass(frozen=True)
class CategoryRow:
    category_id: str
    display_name: str


@dataclass(frozen=True)
class RefundPolicyRow:
    merchant_id: str
    refund_cap_minor: int
    currency: str
    excluded_category_ids: list[str]
    velocity_max_refunds: int
    velocity_window_days: int
    note: str | None


async def get_latest_version(session: AsyncSession) -> VersionRow | None:
    result = await session.execute(
        text(
            f'SELECT version, seed_hash FROM "{SCHEMA}".catalog_versions ORDER BY version DESC LIMIT 1'
        )
    )
    row = result.first()
    if row is None:
        return None
    return VersionRow(version=row.version, seed_hash=row.seed_hash)


async def get_version(session: AsyncSession, version: int) -> VersionRow | None:
    result = await session.execute(
        text(
            f'SELECT version, seed_hash FROM "{SCHEMA}".catalog_versions WHERE version = :v'
        ),
        {"v": version},
    )
    row = result.first()
    if row is None:
        return None
    return VersionRow(version=row.version, seed_hash=row.seed_hash)


async def counts_for_version(session: AsyncSession, version: int) -> tuple[int, int]:
    """Returns (item_count, merchant_count) for the given catalog version, i.e. the
    number of items first visible by that version and merchants seeded overall."""
    result = await session.execute(
        text(
            f'SELECT count(*) FROM "{SCHEMA}".v_items_public WHERE created_in_version <= :v'
        ),
        {"v": version},
    )
    item_count = result.scalar_one()
    result = await session.execute(
        text(f'SELECT count(*) FROM "{SCHEMA}".v_merchants_public')
    )
    merchant_count = result.scalar_one()
    return int(item_count), int(merchant_count)


async def list_items(
    session: AsyncSession,
    *,
    version: int,
    merchant_id: str | None,
    category_id: str | None,
    limit: int,
    offset: int,
) -> list[ItemRow]:
    result = await session.execute(
        text(
            f"""
            SELECT i.sku, i.merchant_id, i.category_id, i.title, i.description, i.active,
                   p.unit_price_minor, p.currency
            FROM "{SCHEMA}".v_items_public i
            JOIN "{SCHEMA}".v_prices_public p ON p.sku = i.sku AND p.catalog_version = :version
            WHERE (CAST(:merchant_id AS text) IS NULL OR i.merchant_id = CAST(:merchant_id AS text))
              AND (CAST(:category_id AS text) IS NULL OR i.category_id = CAST(:category_id AS text))
            ORDER BY i.sku
            LIMIT :limit OFFSET :offset
            """
        ),
        {
            "version": version,
            "merchant_id": merchant_id,
            "category_id": category_id,
            "limit": limit,
            "offset": offset,
        },
    )
    return [
        ItemRow(
            sku=r.sku,
            merchant_id=r.merchant_id,
            category_id=r.category_id,
            title=r.title,
            description=r.description,
            active=r.active,
            unit_price_minor=int(r.unit_price_minor),
            currency=r.currency,
        )
        for r in result.all()
    ]


async def get_item(session: AsyncSession, *, sku: str, version: int) -> ItemRow | None:
    result = await session.execute(
        text(
            f"""
            SELECT i.sku, i.merchant_id, i.category_id, i.title, i.description, i.active,
                   p.unit_price_minor, p.currency
            FROM "{SCHEMA}".v_items_public i
            JOIN "{SCHEMA}".v_prices_public p ON p.sku = i.sku AND p.catalog_version = :version
            WHERE i.sku = :sku
            """
        ),
        {"sku": sku, "version": version},
    )
    row = result.first()
    if row is None:
        return None
    return ItemRow(
        sku=row.sku,
        merchant_id=row.merchant_id,
        category_id=row.category_id,
        title=row.title,
        description=row.description,
        active=row.active,
        unit_price_minor=int(row.unit_price_minor),
        currency=row.currency,
    )


async def list_items_for_resolve(
    session: AsyncSession, *, skus: list[str], version: int
) -> dict[str, ItemRow]:
    """One query for all requested SKUs at a given version (spec.md section 5 step 3)."""
    if not skus:
        return {}
    result = await session.execute(
        text(
            f"""
            SELECT i.sku, i.merchant_id, i.category_id, i.title, i.description, i.active,
                   p.unit_price_minor, p.currency
            FROM "{SCHEMA}".v_items_public i
            JOIN "{SCHEMA}".v_prices_public p ON p.sku = i.sku AND p.catalog_version = :version
            WHERE i.sku = ANY(:skus)
            """
        ),
        {"skus": skus, "version": version},
    )
    rows = {
        r.sku: ItemRow(
            sku=r.sku,
            merchant_id=r.merchant_id,
            category_id=r.category_id,
            title=r.title,
            description=r.description,
            active=r.active,
            unit_price_minor=int(r.unit_price_minor),
            currency=r.currency,
        )
        for r in result.all()
    }
    return rows


async def latest_prices_for_skus(
    session: AsyncSession, *, skus: list[str], version: int
) -> dict[str, int]:
    """unit_price_minor per sku at `version`, used to compute `latest_unit_price_minor`
    when a pinned resolve differs from the current latest version."""
    if not skus:
        return {}
    result = await session.execute(
        text(
            f"""
            SELECT sku, unit_price_minor FROM "{SCHEMA}".v_prices_public
            WHERE sku = ANY(:skus) AND catalog_version = :version
            """
        ),
        {"skus": skus, "version": version},
    )
    return {r.sku: int(r.unit_price_minor) for r in result.all()}


async def list_merchants(session: AsyncSession) -> list[MerchantRow]:
    result = await session.execute(
        text(
            f"SELECT merchant_id, display_name, settlement_alias, currency "
            f'FROM "{SCHEMA}".v_merchants_public ORDER BY merchant_id'
        )
    )
    return [
        MerchantRow(
            merchant_id=r.merchant_id,
            display_name=r.display_name,
            settlement_alias=r.settlement_alias,
            currency=r.currency,
        )
        for r in result.all()
    ]


async def get_merchant(session: AsyncSession, merchant_id: str) -> MerchantRow | None:
    result = await session.execute(
        text(
            f"SELECT merchant_id, display_name, settlement_alias, currency "
            f'FROM "{SCHEMA}".v_merchants_public WHERE merchant_id = :merchant_id'
        ),
        {"merchant_id": merchant_id},
    )
    row = result.first()
    if row is None:
        return None
    return MerchantRow(
        merchant_id=row.merchant_id,
        display_name=row.display_name,
        settlement_alias=row.settlement_alias,
        currency=row.currency,
    )


async def list_categories(session: AsyncSession) -> list[CategoryRow]:
    result = await session.execute(
        text(
            f'SELECT category_id, display_name FROM "{SCHEMA}".v_categories_public ORDER BY category_id'
        )
    )
    return [
        CategoryRow(category_id=r.category_id, display_name=r.display_name)
        for r in result.all()
    ]


async def get_refund_policy(
    session: AsyncSession, merchant_id: str
) -> RefundPolicyRow | None:
    result = await session.execute(
        text(
            f"""
            SELECT merchant_id, refund_cap_minor, excluded_category_ids, velocity_max_refunds,
                   velocity_window_days, note
            FROM "{SCHEMA}".merchant_refund_policy_seeds
            WHERE merchant_id = :merchant_id
            """
        ),
        {"merchant_id": merchant_id},
    )
    row = result.first()
    if row is None:
        return None
    return RefundPolicyRow(
        merchant_id=row.merchant_id,
        refund_cap_minor=int(row.refund_cap_minor),
        currency="USD",
        excluded_category_ids=list(row.excluded_category_ids or []),
        velocity_max_refunds=row.velocity_max_refunds,
        velocity_window_days=row.velocity_window_days,
        note=row.note,
    )
