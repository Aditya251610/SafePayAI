"""api-gateway baseline: schema, tables, grants

Tables per .claude/prd/services/api-gateway/spec.md section 3: users, sessions,
csrf_uses, signing_keys, settings. Grants via libs/common's
safepayai_common.db.grants helper per docs/service-skeleton-conventions.md section 9.

Role naming note (flagged conflict): api-gateway/deployment.md section 1 and
spec.md section 3 call the runtime role `gateway_app`. The binding conventions doc
(section 9) and data-architecture.md section 4 use the generic `mig_<slug>` /
`svc_<slug>` scheme (`mig_apigateway` / `svc_apigateway`). Per the conventions
doc's tie-break rule, this migration uses `mig_apigateway` / `svc_apigateway`.
Flagged for the api-gateway owner.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-11
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from safepayai_common.db.grants import TableGrant, apply_table_grants, create_schema_and_roles

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "gateway"
MIGRATION_ROLE = "mig_apigateway"
RUNTIME_ROLE = "svc_apigateway"


def upgrade() -> None:
    bind = op.get_bind()

    for role in (MIGRATION_ROLE, RUNTIME_ROLE):
        bind.execute(
            sa.text(
                f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                        CREATE ROLE "{role}" NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS LOGIN;
                    END IF;
                END $$;
                """
            )
        )

    create_schema_and_roles(bind, SCHEMA, MIGRATION_ROLE, RUNTIME_ROLE)

    bind.execute(sa.text('CREATE EXTENSION IF NOT EXISTS pgcrypto'))

    op.execute(f'''
        CREATE TABLE "{SCHEMA}"."users" (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            handle text UNIQUE,
            role text NOT NULL,
            actor_type text NOT NULL,
            display_name text,
            password_hash text,
            is_ephemeral boolean NOT NULL DEFAULT false,
            epoch integer NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now(),
            disabled_at timestamptz
        )
    ''')

    op.execute(f'''
        CREATE TABLE "{SCHEMA}"."sessions" (
            sid_hash text PRIMARY KEY,
            user_id uuid NOT NULL REFERENCES "{SCHEMA}"."users"(id),
            role text NOT NULL,
            epoch integer NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            last_seen_at timestamptz NOT NULL DEFAULT now(),
            expires_at timestamptz NOT NULL,
            ip_hash text,
            ua_hash text
        )
    ''')
    op.execute(f'CREATE INDEX IF NOT EXISTS idx_sessions_user ON "{SCHEMA}"."sessions"(user_id)')

    op.execute(f'''
        CREATE TABLE "{SCHEMA}"."csrf_uses" (
            jti uuid PRIMARY KEY,
            sid_hash text NOT NULL,
            purpose text NOT NULL,
            expires_at timestamptz NOT NULL
        )
    ''')

    op.execute(f'''
        CREATE TABLE "{SCHEMA}"."signing_keys" (
            kid text PRIMARY KEY,
            alg text NOT NULL,
            public_key_pem text NOT NULL,
            status text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            retire_after timestamptz
        )
    ''')

    op.execute(f'''
        CREATE TABLE "{SCHEMA}"."settings" (
            key text PRIMARY KEY,
            value text
        )
    ''')

    grants = [
        TableGrant("users", ("SELECT", "INSERT", "UPDATE")),
        TableGrant("sessions", ("SELECT", "INSERT", "UPDATE", "DELETE")),
        TableGrant("csrf_uses", ("SELECT", "INSERT", "DELETE")),
        TableGrant("signing_keys", ("SELECT",)),
        TableGrant("settings", ("SELECT",)),
    ]
    apply_table_grants(bind, SCHEMA, RUNTIME_ROLE, grants)


def downgrade() -> None:
    op.execute(f'DROP TABLE IF EXISTS "{SCHEMA}"."settings"')
    op.execute(f'DROP TABLE IF EXISTS "{SCHEMA}"."signing_keys"')
    op.execute(f'DROP TABLE IF EXISTS "{SCHEMA}"."csrf_uses"')
    op.execute(f'DROP TABLE IF EXISTS "{SCHEMA}"."sessions"')
    op.execute(f'DROP TABLE IF EXISTS "{SCHEMA}"."users"')
    op.execute(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE')
