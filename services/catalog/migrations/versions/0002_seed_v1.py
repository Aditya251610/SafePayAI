"""catalog seed v1: 12 items / 3 merchants

Loads services/catalog/app/seed/catalog_seed.json (committed, single source) per
.claude/prd/services/catalog/spec.md section 2 and section 10 of data-architecture.md.
catalog is read-only at runtime (service-map), so this data migration is the only
data migration in Wave 4 (conventions doc section 9).

Revision ID: 0002_seed_v1
Revises: 0001_baseline
Create Date: 2026-10-11
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_seed_v1"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "catalog"
SEED_PATH = pathlib.Path(__file__).resolve().parents[2] / "app" / "seed" / "catalog_seed.json"


def _load_seed() -> dict:
    raw = SEED_PATH.read_text(encoding="utf-8")
    return json.loads(raw), raw


def upgrade() -> None:
    bind = op.get_bind()
    data, raw_text = _load_seed()
    seed_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    version = data["version"]

    bind.execute(
        sa.text(f'INSERT INTO "{SCHEMA}"."catalog_versions" (version, seed_hash, reason) VALUES (:v, :h, :r)'),
        {"v": version, "h": seed_hash, "r": "initial_seed"},
    )

    for m in data["merchants"]:
        bind.execute(
            sa.text(
                f'INSERT INTO "{SCHEMA}"."merchants" (merchant_id, display_name, description, active) '
                "VALUES (:merchant_id, :display_name, :description, :active)"
            ),
            {
                "merchant_id": m["merchant_id"],
                "display_name": m["display_name"],
                "description": m.get("description"),
                "active": m["active"],
            },
        )
        bind.execute(
            sa.text(
                f'INSERT INTO "{SCHEMA}"."merchant_settlement_map" (merchant_id, settlement_alias, currency) '
                "VALUES (:merchant_id, :settlement_alias, :currency)"
            ),
            {
                "merchant_id": m["merchant_id"],
                "settlement_alias": m["settlement_alias"],
                "currency": m["currency"],
            },
        )

    for c in data["categories"]:
        bind.execute(
            sa.text(f'INSERT INTO "{SCHEMA}"."categories" (category_id, display_name) VALUES (:category_id, :display_name)'),
            {"category_id": c["category_id"], "display_name": c["display_name"]},
        )

    for item in data["items"]:
        bind.execute(
            sa.text(
                f'INSERT INTO "{SCHEMA}"."items" '
                "(sku, merchant_id, category_id, title, description, active, created_in_version) "
                "VALUES (:sku, :merchant_id, :category_id, :title, :description, :active, :version)"
            ),
            {
                "sku": item["sku"],
                "merchant_id": item["merchant_id"],
                "category_id": item["category_id"],
                "title": item["title"],
                "description": item["description"],
                "active": item["active"],
                "version": version,
            },
        )
        bind.execute(
            sa.text(
                f'INSERT INTO "{SCHEMA}"."item_prices" (sku, catalog_version, unit_price_minor, currency) '
                "VALUES (:sku, :version, :price, :currency)"
            ),
            {
                "sku": item["sku"],
                "version": version,
                "price": item["unit_price_minor"],
                "currency": item["currency"],
            },
        )

    for seed in data["merchant_refund_policy_seeds"]:
        bind.execute(
            sa.text(
                f'INSERT INTO "{SCHEMA}"."merchant_refund_policy_seeds" '
                "(merchant_id, refund_cap_minor, excluded_category_ids, velocity_max_refunds, velocity_window_days, note) "
                "VALUES (:merchant_id, :refund_cap_minor, :excluded, :velocity_max, :velocity_window, :note)"
            ),
            {
                "merchant_id": seed["merchant_id"],
                "refund_cap_minor": seed["refund_cap_minor"],
                "excluded": seed["excluded_category_ids"],
                "velocity_max": seed["velocity_max_refunds"],
                "velocity_window": seed["velocity_window_days"],
                "note": seed.get("note"),
            },
        )

    for fixture in data["item_fixtures"]:
        bind.execute(
            sa.text(
                f'INSERT INTO "{SCHEMA}"."item_fixtures" (sku, kind, expected_behavior, target_sku) '
                "VALUES (:sku, :kind, :expected_behavior, :target_sku)"
            ),
            {
                "sku": fixture["sku"],
                "kind": fixture["kind"],
                "expected_behavior": fixture["expected_behavior"],
                "target_sku": fixture.get("target_sku"),
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    for table in (
        "item_fixtures",
        "merchant_refund_policy_seeds",
        "item_prices",
        "items",
        "categories",
        "merchant_settlement_map",
        "merchants",
        "catalog_versions",
    ):
        bind.execute(sa.text(f'DELETE FROM "{SCHEMA}"."{table}"'))
