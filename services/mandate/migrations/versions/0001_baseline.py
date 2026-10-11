"""mandate baseline: schema, tables, immutability triggers, grants

Tables per .claude/prd/services/mandate/spec.md sections 2-12 (superset of
data-architecture.md section 3's mandate row, additive per spec.md C4). Grants via
libs/common's safepayai_common.db.grants helper per conventions doc section 9.

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

SCHEMA = "mandate"
MIGRATION_ROLE = "mig_mandate"
RUNTIME_ROLE = "svc_mandate"

IMMUTABLE_TABLES = ("mandates", "revocations", "nonces", "nonce_uses", "protection_grants", "mandate_attestations")


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

    op.execute(f'''
        CREATE TABLE "{SCHEMA}"."mandates" (
            mandate_id uuid PRIMARY KEY,
            buyer_id text NOT NULL,
            schema text NOT NULL,
            currency char(3) NOT NULL,
            max_total_minor bigint NOT NULL CHECK (max_total_minor > 0),
            max_qty_per_line integer NOT NULL,
            merchant_allowlist jsonb NOT NULL,
            intent_text text NOT NULL,
            expires_at timestamptz NOT NULL,
            protection jsonb NOT NULL,
            revoke_effect text NOT NULL,
            policy_version text NOT NULL,
            nonce text NOT NULL,
            render_version text NOT NULL,
            screen_text_hash text NOT NULL,
            canonical_json text NOT NULL,
            mandate_hash text NOT NULL,
            hmac text NOT NULL,
            hmac_alg text NOT NULL,
            hmac_key_id text NOT NULL,
            signed_at timestamptz NOT NULL DEFAULT now(),
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (nonce)
        )
    ''')
    op.execute(f'CREATE INDEX IF NOT EXISTS idx_mandates_buyer ON "{SCHEMA}"."mandates"(buyer_id, created_at DESC)')

    op.execute(f'''
        CREATE TABLE "{SCHEMA}"."revocations" (
            mandate_id uuid NOT NULL UNIQUE REFERENCES "{SCHEMA}"."mandates"(mandate_id),
            revoked_at timestamptz NOT NULL DEFAULT now(),
            reason_code text NOT NULL,
            actor_ref text
        )
    ''')

    op.execute(f'''
        CREATE TABLE "{SCHEMA}"."mandate_spend" (
            mandate_id uuid PRIMARY KEY REFERENCES "{SCHEMA}"."mandates"(mandate_id),
            max_total_minor bigint NOT NULL,
            spent_minor bigint NOT NULL DEFAULT 0 CHECK (spent_minor >= 0),
            reserved_minor bigint NOT NULL DEFAULT 0 CHECK (reserved_minor >= 0),
            version integer NOT NULL DEFAULT 1,
            updated_at timestamptz NOT NULL DEFAULT now(),
            CHECK (spent_minor + reserved_minor <= max_total_minor)
        )
    ''')

    op.execute(f'''
        CREATE TABLE "{SCHEMA}"."spend_reservations" (
            reservation_id uuid PRIMARY KEY,
            mandate_id uuid NOT NULL REFERENCES "{SCHEMA}"."mandates"(mandate_id),
            order_id uuid NOT NULL,
            amount_minor bigint NOT NULL,
            currency char(3) NOT NULL,
            proposal_hash text,
            state text NOT NULL,
            expires_at timestamptz,
            authorized_at timestamptz,
            captured_at timestamptz,
            capture_id text,
            release_reason text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (mandate_id, order_id)
        )
    ''')
    op.execute(f'CREATE INDEX IF NOT EXISTS idx_spend_res_mandate_state ON "{SCHEMA}"."spend_reservations"(mandate_id, state)')

    op.execute(f'''
        CREATE TABLE "{SCHEMA}"."protection_grants" (
            grant_id uuid PRIMARY KEY,
            mandate_id uuid NOT NULL REFERENCES "{SCHEMA}"."mandates"(mandate_id),
            order_id uuid NOT NULL UNIQUE,
            capture_id text NOT NULL UNIQUE,
            buyer_id text NOT NULL,
            mandate_hash text NOT NULL,
            terms jsonb NOT NULL,
            terms_hash text NOT NULL,
            captured_amount_minor bigint NOT NULL,
            captured_at timestamptz NOT NULL,
            grant_hmac text NOT NULL,
            hmac_key_id text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    ''')
    op.execute(f'CREATE INDEX IF NOT EXISTS idx_grants_mandate ON "{SCHEMA}"."protection_grants"(mandate_id)')

    op.execute(f'''
        CREATE TABLE "{SCHEMA}"."nonces" (
            nonce_hash text PRIMARY KEY,
            buyer_id text NOT NULL,
            purpose text NOT NULL,
            terms_digest text NOT NULL,
            issued_at timestamptz NOT NULL DEFAULT now(),
            expires_at timestamptz NOT NULL
        )
    ''')

    op.execute(f'''
        CREATE TABLE "{SCHEMA}"."nonce_uses" (
            nonce_hash text PRIMARY KEY,
            mandate_id uuid NOT NULL REFERENCES "{SCHEMA}"."mandates"(mandate_id),
            used_at timestamptz NOT NULL DEFAULT now()
        )
    ''')

    op.execute(f'''
        CREATE TABLE "{SCHEMA}"."idempotency_keys" (
            scope text NOT NULL,
            key text NOT NULL,
            request_hash text NOT NULL,
            response jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (scope, key)
        )
    ''')

    op.execute(f'''
        CREATE TABLE "{SCHEMA}"."outbox" (
            seq bigserial PRIMARY KEY,
            event_id uuid NOT NULL UNIQUE,
            type text NOT NULL,
            version integer NOT NULL DEFAULT 1,
            aggregate_id text NOT NULL,
            payload jsonb NOT NULL,
            trace_id text,
            created_at timestamptz NOT NULL DEFAULT now(),
            delivered_to jsonb NOT NULL DEFAULT '{{}}',
            attempts integer NOT NULL DEFAULT 0,
            next_attempt_at timestamptz
        )
    ''')
    op.execute(f'CREATE INDEX IF NOT EXISTS idx_outbox_next_attempt ON "{SCHEMA}"."outbox"(next_attempt_at)')

    op.execute(f'''
        CREATE TABLE "{SCHEMA}"."mandate_attestations" (
            id uuid PRIMARY KEY,
            mandate_id uuid NOT NULL REFERENCES "{SCHEMA}"."mandates"(mandate_id),
            key_id text NOT NULL,
            hmac text NOT NULL,
            attested_at timestamptz NOT NULL DEFAULT now(),
            reason text
        )
    ''')

    # Immutability triggers (BEFORE UPDATE OR DELETE raise) per spec.md section 6/migration notes.
    op.execute(f'''
        CREATE OR REPLACE FUNCTION "{SCHEMA}".reject_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'row is immutable: % on %.%', TG_OP, TG_TABLE_SCHEMA, TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql;
    ''')
    for table in IMMUTABLE_TABLES:
        op.execute(f'''
            CREATE TRIGGER trg_{table}_immutable
            BEFORE UPDATE OR DELETE ON "{SCHEMA}"."{table}"
            FOR EACH ROW EXECUTE FUNCTION "{SCHEMA}".reject_mutation();
        ''')

    # mandate_spend: only max_total_minor is protected (spent_minor/reserved_minor/version/updated_at move).
    op.execute(f'''
        CREATE OR REPLACE FUNCTION "{SCHEMA}".reject_max_total_change() RETURNS trigger AS $$
        BEGIN
            IF NEW.max_total_minor <> OLD.max_total_minor THEN
                RAISE EXCEPTION 'mandate_spend.max_total_minor is immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    ''')
    op.execute(f'''
        CREATE TRIGGER trg_mandate_spend_max_total_immutable
        BEFORE UPDATE ON "{SCHEMA}"."mandate_spend"
        FOR EACH ROW EXECUTE FUNCTION "{SCHEMA}".reject_max_total_change();
    ''')

    grants = [
        TableGrant("mandates", ("INSERT", "SELECT")),
        TableGrant("revocations", ("INSERT", "SELECT")),
        TableGrant("nonces", ("INSERT", "SELECT")),
        TableGrant("nonce_uses", ("INSERT", "SELECT")),
        TableGrant("protection_grants", ("INSERT", "SELECT")),
        TableGrant("mandate_attestations", ("INSERT", "SELECT")),
        TableGrant("mandate_spend", ("INSERT", "SELECT", "UPDATE")),
        TableGrant("spend_reservations", ("INSERT", "SELECT", "UPDATE")),
        TableGrant("idempotency_keys", ("INSERT", "SELECT")),
        TableGrant("outbox", ("INSERT", "SELECT", "UPDATE")),
    ]
    apply_table_grants(bind, SCHEMA, RUNTIME_ROLE, grants)


def downgrade() -> None:
    op.execute(f'DROP TABLE IF EXISTS "{SCHEMA}"."mandate_attestations"')
    op.execute(f'DROP TABLE IF EXISTS "{SCHEMA}"."outbox"')
    op.execute(f'DROP TABLE IF EXISTS "{SCHEMA}"."idempotency_keys"')
    op.execute(f'DROP TABLE IF EXISTS "{SCHEMA}"."nonce_uses"')
    op.execute(f'DROP TABLE IF EXISTS "{SCHEMA}"."nonces"')
    op.execute(f'DROP TABLE IF EXISTS "{SCHEMA}"."protection_grants"')
    op.execute(f'DROP TABLE IF EXISTS "{SCHEMA}"."spend_reservations"')
    op.execute(f'DROP TABLE IF EXISTS "{SCHEMA}"."mandate_spend"')
    op.execute(f'DROP TABLE IF EXISTS "{SCHEMA}"."revocations"')
    op.execute(f'DROP TABLE IF EXISTS "{SCHEMA}"."mandates"')
    op.execute(f'DROP FUNCTION IF EXISTS "{SCHEMA}".reject_max_total_change()')
    op.execute(f'DROP FUNCTION IF EXISTS "{SCHEMA}".reject_mutation()')
    op.execute(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE')
