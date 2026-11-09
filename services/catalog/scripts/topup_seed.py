"""Idempotently top up an already-migrated catalog DB from catalog_seed.json.

Migrations are applied once, so a deployed DB does not see seed growth. This inserts any
missing categories/items/prices for the CURRENT catalog version using
INSERT ... ON CONFLICT DO NOTHING. It never updates or deletes rows and never bumps the
version. Prints counts only.

    uv run python scripts/topup_seed.py [--dry-run]

Env: PS_CATALOG_MIGRATION_DATABASE_URL (preferred) or PS_CATALOG_DATABASE_URL.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys

import asyncpg

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app_catalog.topup import plan_topup

SCHEMA = "catalog"
SEED_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "app_catalog"
    / "seed"
    / "catalog_seed.json"
)


def _dsn() -> str:
    url = os.environ.get("PS_CATALOG_MIGRATION_DATABASE_URL") or os.environ.get(
        "PS_CATALOG_DATABASE_URL"
    )
    if not url:
        raise SystemExit(
            "PS_CATALOG_MIGRATION_DATABASE_URL (or PS_CATALOG_DATABASE_URL) is not set"
        )
    scheme, sep, rest = url.partition("://")
    return scheme.split("+")[0] + sep + rest


async def run(dry_run: bool) -> dict[str, int]:
    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    conn = await asyncpg.connect(_dsn())
    try:
        async with conn.transaction():
            version = await conn.fetchval(
                f'SELECT max(version) FROM "{SCHEMA}".catalog_versions'
            )
            if version is None:
                raise SystemExit("catalog has no seeded version; run migrations first")
            merchants = [
                r[0]
                for r in await conn.fetch(
                    f'SELECT merchant_id FROM "{SCHEMA}".merchants'
                )
            ]
            cats = [
                r[0]
                for r in await conn.fetch(
                    f'SELECT category_id FROM "{SCHEMA}".categories'
                )
            ]
            skus = [r[0] for r in await conn.fetch(f'SELECT sku FROM "{SCHEMA}".items')]
            priced = [
                r[0]
                for r in await conn.fetch(
                    f'SELECT sku FROM "{SCHEMA}".item_prices WHERE catalog_version = $1',
                    version,
                )
            ]
            plan = plan_topup(
                seed,
                existing_merchants=merchants,
                existing_categories=cats,
                existing_skus=skus,
                priced_skus=priced,
            )
            if not dry_run:
                await conn.executemany(
                    f'INSERT INTO "{SCHEMA}".categories (category_id, display_name) '
                    "VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    [(c["category_id"], c["display_name"]) for c in plan.categories],
                )
                await conn.executemany(
                    f'INSERT INTO "{SCHEMA}".items '
                    "(sku, merchant_id, category_id, title, description, active, created_in_version) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7) ON CONFLICT DO NOTHING",
                    [
                        (
                            i["sku"],
                            i["merchant_id"],
                            i["category_id"],
                            i["title"],
                            i["description"],
                            i["active"],
                            version,
                        )
                        for i in plan.items
                    ],
                )
                await conn.executemany(
                    f'INSERT INTO "{SCHEMA}".item_prices '
                    "(sku, catalog_version, unit_price_minor, currency) "
                    "VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING",
                    [
                        (p["sku"], version, p["unit_price_minor"], p["currency"])
                        for p in plan.prices
                    ],
                )
    finally:
        await conn.close()
    return plan.counts()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="plan only, no writes")
    args = parser.parse_args()
    counts = asyncio.run(run(args.dry_run))
    label = "would insert" if args.dry_run else "inserted"
    print(f"{label}: " + ", ".join(f"{k}={v}" for k, v in counts.items()))


if __name__ == "__main__":
    main()
