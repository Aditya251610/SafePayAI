"""Seed script for the gateway's seeded accounts (spec.md section 3 / sprint-tasks
GW-S1-04/05): one login per real catalog merchant (real multi-tenant identity,
replacing the former single shared "merchant" demo login), operator, and an
optional buyer persona. Hashes are made here, at seed time, from env-provided
passwords; the running app never reads `SEED_*` (per spec.md section 13).

Usage:
    uv run python scripts/seed.py

Reads:
    SEED_MERCHANT_TRAILHEAD_PASSWORD   (required)
    SEED_MERCHANT_HEARTH_PASSWORD      (required)
    SEED_MERCHANT_PIXELWIRE_PASSWORD   (required)
    SEED_OPERATOR_PASSWORD             (required)
    SEED_BUYER_PASSWORD                (optional - skips the buyer persona if unset)
    PS_APIGATEWAY_DATABASE_URL (or PS_APIGATEWAY_MIGRATION_DATABASE_URL)

Idempotent: upserts by handle, re-hashing the password every run (so rotating a
SEED_* value and re-running updates the stored hash, per GW-I01's "seed script
idempotent" requirement).
"""

from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.auth.passwords import hash_password

SEED_USERS = [
    # handle, role, actor_type, display_name, password env var, required, merchant_id
    (
        "merchant-trailhead",
        "merchant",
        "merchant",
        "Trailhead (demo merchant)",
        "SEED_MERCHANT_TRAILHEAD_PASSWORD",
        True,
        "mrc_trailhead",
    ),
    (
        "merchant-hearth",
        "merchant",
        "merchant",
        "Hearth (demo merchant)",
        "SEED_MERCHANT_HEARTH_PASSWORD",
        True,
        "mrc_hearth",
    ),
    (
        "merchant-pixelwire",
        "merchant",
        "merchant",
        "Pixelwire (demo merchant)",
        "SEED_MERCHANT_PIXELWIRE_PASSWORD",
        True,
        "mrc_pixelwire",
    ),
    (
        "operator",
        "operator",
        "operator",
        "Operator (demo)",
        "SEED_OPERATOR_PASSWORD",
        True,
        None,
    ),
    (
        "buyer-persona",
        "buyer",
        "buyer",
        "Buyer persona (demo)",
        "SEED_BUYER_PASSWORD",
        False,
        None,
    ),
]


async def main() -> None:
    database_url = os.environ.get(
        "PS_APIGATEWAY_MIGRATION_DATABASE_URL"
    ) or os.environ.get("PS_APIGATEWAY_DATABASE_URL")
    if not database_url:
        raise SystemExit(
            "PS_APIGATEWAY_DATABASE_URL (or _MIGRATION_DATABASE_URL) is not set"
        )

    engine = create_async_engine(database_url)
    async with engine.begin() as conn:
        for (
            handle,
            role,
            actor_type,
            display_name,
            env_var,
            required,
            merchant_id,
        ) in SEED_USERS:
            password = os.environ.get(env_var)
            if not password:
                if required:
                    raise SystemExit(
                        f"{env_var} is not set (required to seed {handle!r})"
                    )
                print(f"skipping {handle!r}: {env_var} not set")
                continue

            password_hash = hash_password(password)
            await conn.execute(
                text(
                    """
                    INSERT INTO "gateway"."users"
                        (handle, role, actor_type, display_name, password_hash,
                         is_ephemeral, epoch, merchant_id)
                    VALUES (:handle, :role, :actor_type, :display_name, :password_hash,
                            false, 0, :merchant_id)
                    ON CONFLICT (handle) DO UPDATE SET
                        password_hash = EXCLUDED.password_hash,
                        role = EXCLUDED.role,
                        actor_type = EXCLUDED.actor_type,
                        display_name = EXCLUDED.display_name,
                        merchant_id = EXCLUDED.merchant_id
                    """
                ),
                {
                    "handle": handle,
                    "role": role,
                    "actor_type": actor_type,
                    "display_name": display_name,
                    "password_hash": password_hash,
                    "merchant_id": merchant_id,
                },
            )
            print(f"seeded {handle!r} (role={role}, merchant_id={merchant_id})")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
