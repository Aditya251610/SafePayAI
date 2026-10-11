"""audit baseline: schema, roles, entries/verify_runs/head_exports tables,
append-only + linkage triggers, genesis row.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-11

Scope (service-skeleton-conventions.md sec 9): one baseline revision creating the audit
schema's objects exactly as documented in:
  - architecture/data-architecture.md sec 3/4 (entries table shape, svc_audit grants)
  - services/audit/spec.md sec 2 (verify_runs, head_exports, full entries column list),
    sec 3 (concurrency/linkage design), sec 4 (hash domain string), sec 8 (roles/grants/
    triggers), sec 10 (genesis row)

Deviations/flags (see also the audit scaffolding handoff):
  1. Role creation: libs/common/safepayai_common/db/grants.py only does
     CREATE SCHEMA / REVOKE / GRANT USAGE + per-table grants -- it has no CREATE ROLE.
     Role creation below is audit-specific raw SQL filling that gap; no passwords are
     ever set here (Neon console/platform secret store sets them out-of-band, per
     spec.md sec 8's "passwords never in docs or repo" rule).
  2. `entries.seq`: data-architecture.md sec 3's one-line table listing says
     "seq bigint identity pk". audit's own spec.md sec 2.1 and sec 3 are explicit and
     detailed that `seq` is writer-assigned ("not a sequence") so the advisory-lock
     append algorithm (REQ-AU-003) can guarantee gaplessness under concurrency -- a
     GENERATED ALWAYS/BY DEFAULT AS IDENTITY column does not give that guarantee (a
     rolled-back insert still burns a sequence value). This migration follows spec.md's
     detailed concurrency design over data-architecture.md's summary line: plain
     `BIGINT PRIMARY KEY`, no identity/sequence. Flagged for the data-architecture.md
     owner to reconcile the summary table.
  3. The BEFORE INSERT linkage trigger and the genesis-row hash computation are
     audit-specific DDL/seed logic the shared grants helper doesn't (and shouldn't)
     know about, per the task brief's own carve-out.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from safepayai_common.db.grants import (
    ROLE_FLAGS,
    TableGrant,
    apply_table_grants,
    create_schema_and_roles,
)
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "audit"
OWNER_ROLE = "audit_owner"
APP_ROLE = "audit_app"

# Domain-separated hash prefix (post-rename; never "madewhole.audit.v1" -- spec.md sec 4).
HASH_DOMAIN = b"safepayai.audit.v1\n"
GENESIS_PREV_HASH = "0" * 64

# Constant advisory-lock key shared by the append path (spec.md sec 3 step 2/6) and the
# BEFORE INSERT linkage trigger (step 6, "re-entrant in the same txn"). Arbitrary but
# fixed 63-bit constant; must match whatever app/chain/append.py uses in Wave 5.
ADVISORY_LOCK_KEY = 727274726269743139


def _jcs_bytes(obj: dict) -> bytes:
    """Minimal RFC 8785-compatible canonicalization for the FIXED genesis content object.

    Sufficient here because the genesis payload has only ASCII keys/string values and no
    floats (sorted keys, no whitespace, UTF-8). The general-purpose canonicalizer with
    full unicode/number-edge-case handling is Wave 5's app/chain/canonical.py; this is
    not a reimplementation of that module, just enough to seed a correct genesis hash.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _row_hash(prev_hash: str, canonical: bytes) -> str:
    return hashlib.sha256(HASH_DOMAIN + prev_hash.encode("ascii") + b"\n" + canonical).hexdigest()


def upgrade() -> None:
    conn = op.get_bind()

    # --- Roles (gap in the shared grants helper; see module docstring item 1) ---
    conn.execute(
        text(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{OWNER_ROLE}') THEN
                    CREATE ROLE {OWNER_ROLE} {ROLE_FLAGS.replace("LOGIN", "NOLOGIN")};
                END IF;
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                    CREATE ROLE {APP_ROLE} {ROLE_FLAGS};
                END IF;
            END $$;
            """
        )
    )
    # audit_owner is NOLOGIN by design: spec.md sec 8 "used only by migrations/CI, never
    # in the running service" -- migrations/CI connect as a bootstrap admin and SET ROLE,
    # or Neon's console/API manages a login-capable owner credential outside this file.

    # --- Schema + base USAGE grant (shared helper) ---
    create_schema_and_roles(conn, schema=SCHEMA, migration_role=OWNER_ROLE, runtime_role=APP_ROLE)
    conn.execute(text(f'ALTER SCHEMA "{SCHEMA}" OWNER TO {OWNER_ROLE}'))
    conn.execute(text(f"ALTER ROLE {APP_ROLE} SET search_path = {SCHEMA}"))

    # --- audit.entries (data-architecture.md sec 3, spec.md sec 2.1) ---
    op.create_table(
        "entries",
        sa.Column("seq", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("chain_id", sa.Text(), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False),
        sa.Column("producer", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_type", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.Text(), nullable=False),
        sa.Column("auth_method", sa.Text(), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("trace_id", sa.Text(), nullable=False),
        sa.Column("buyer_id", sa.Text(), nullable=True),
        sa.Column("mandate_id", sa.Text(), nullable=True),
        sa.Column("order_id", sa.Text(), nullable=True),
        sa.Column("case_id", sa.Text(), nullable=True),
        sa.Column("canonical", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("prev_hash", sa.CHAR(64), nullable=False),
        sa.Column("row_hash", sa.CHAR(64), nullable=False),
        sa.UniqueConstraint("event_id", name="uq_entries_event_id"),
        sa.UniqueConstraint("prev_hash", name="uq_entries_prev_hash"),
        sa.UniqueConstraint("row_hash", name="uq_entries_row_hash"),
        schema=SCHEMA,
    )

    # Indexing per spec.md sec 9 (grid filters, role scoping, fork-guard lookups).
    op.create_index(
        "ix_entries_mandate_id",
        "entries",
        ["mandate_id", "seq"],
        unique=False,
        schema=SCHEMA,
        postgresql_where=sa.text("mandate_id IS NOT NULL"),
    )
    op.create_index(
        "ix_entries_order_id",
        "entries",
        ["order_id", "seq"],
        unique=False,
        schema=SCHEMA,
        postgresql_where=sa.text("order_id IS NOT NULL"),
    )
    op.create_index(
        "ix_entries_case_id",
        "entries",
        ["case_id", "seq"],
        unique=False,
        schema=SCHEMA,
        postgresql_where=sa.text("case_id IS NOT NULL"),
    )
    op.create_index(
        "ix_entries_buyer_id",
        "entries",
        ["buyer_id", "seq"],
        unique=False,
        schema=SCHEMA,
        postgresql_where=sa.text("buyer_id IS NOT NULL"),
    )
    op.create_index(
        "ix_entries_event_type", "entries", ["event_type", "seq"], unique=False, schema=SCHEMA
    )
    op.create_index(
        "ix_entries_actor",
        "entries",
        ["actor_type", "actor_id", "seq"],
        unique=False,
        schema=SCHEMA,
    )
    op.create_index("ix_entries_request_id", "entries", ["request_id"], unique=False, schema=SCHEMA)

    # --- audit.verify_runs (spec.md sec 2.2, informational, NOT hashed) ---
    op.create_table(
        "verify_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("head_seq_at_start", sa.BigInteger(), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=True),
        sa.Column("first_bad_seq", sa.BigInteger(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("requested_by_actor_id", sa.Text(), nullable=True),
        sa.Column("request_id", sa.Text(), nullable=True),
        schema=SCHEMA,
    )

    # --- audit.head_exports (spec.md sec 2.3, informational) ---
    op.create_table(
        "head_exports",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("row_hash", sa.CHAR(64), nullable=False),
        sa.Column("signature", sa.Text(), nullable=True),
        sa.Column("requested_by_actor_id", sa.Text(), nullable=True),
        schema=SCHEMA,
    )

    # --- Grants: audit_app gets INSERT+SELECT only on the three tables (spec.md sec 8) ---
    apply_table_grants(
        conn,
        schema=SCHEMA,
        runtime_role=APP_ROLE,
        grants=[
            TableGrant("entries", ("INSERT", "SELECT")),
            TableGrant("verify_runs", ("INSERT", "SELECT")),
            TableGrant("head_exports", ("INSERT", "SELECT")),
        ],
    )
    # `verify_runs.id` and `head_exports.id` are SERIAL (autoincrement) PKs, which are
    # backed by an implicit sequence owned by audit_owner -- INSERT privilege on the
    # TABLE does not imply USAGE on that SEQUENCE (unlike `entries.seq`, which is
    # writer-assigned, not a sequence, per this migration's own docstring item 2, so it
    # needs no sequence grant at all). Without this, `audit_app` gets
    # "permission denied for sequence ..._id_seq" on its very first INSERT.
    conn.execute(text(f"GRANT USAGE ON SEQUENCE {SCHEMA}.verify_runs_id_seq TO {APP_ROLE}"))
    conn.execute(text(f"GRANT USAGE ON SEQUENCE {SCHEMA}.head_exports_id_seq TO {APP_ROLE}"))

    # --- Triggers (audit-specific DDL; not covered by the shared grants helper) ---
    conn.execute(
        text(
            f"""
            CREATE OR REPLACE FUNCTION {SCHEMA}.audit_reject_mutation() RETURNS trigger
            LANGUAGE plpgsql
            SECURITY INVOKER
            SET search_path = {SCHEMA}, pg_temp
            AS $fn$
            BEGIN
                RAISE EXCEPTION
                    'audit_is_append_only: % is not permitted on {SCHEMA}.entries', TG_OP
                    USING ERRCODE = 'insufficient_privilege';
            END;
            $fn$;
            """
        )
    )
    conn.execute(text(f"ALTER FUNCTION {SCHEMA}.audit_reject_mutation() OWNER TO {OWNER_ROLE}"))

    conn.execute(
        text(
            f"""
            CREATE TRIGGER trg_entries_reject_update_delete
                BEFORE UPDATE OR DELETE ON {SCHEMA}.entries
                FOR EACH ROW EXECUTE FUNCTION {SCHEMA}.audit_reject_mutation();
            """
        )
    )
    conn.execute(
        text(
            f"""
            CREATE TRIGGER trg_entries_reject_truncate
                BEFORE TRUNCATE ON {SCHEMA}.entries
                FOR EACH STATEMENT EXECUTE FUNCTION {SCHEMA}.audit_reject_mutation();
            """
        )
    )

    conn.execute(
        text(
            f"""
            CREATE OR REPLACE FUNCTION {SCHEMA}.audit_check_linkage() RETURNS trigger
            LANGUAGE plpgsql
            SECURITY INVOKER
            SET search_path = {SCHEMA}, pg_temp
            AS $fn$
            DECLARE
                head_seq BIGINT;
                head_hash CHAR(64);
            BEGIN
                -- Re-entrant within the appender's own transaction (spec.md sec 3 step 6):
                -- the appender already holds this lock, so this is a no-op re-acquire; it
                -- is also the guard against a second/buggy writer that skipped the lock.
                PERFORM pg_advisory_xact_lock({ADVISORY_LOCK_KEY});

                SELECT seq, row_hash INTO head_seq, head_hash
                    FROM {SCHEMA}.entries ORDER BY seq DESC LIMIT 1;

                IF head_seq IS NULL THEN
                    IF NEW.seq <> 1 OR NEW.prev_hash <> repeat('0', 64) THEN
                        RAISE EXCEPTION
                            'audit_linkage_violation: first row must be seq=1'
                            ' with zero prev_hash (genesis)'
                            USING ERRCODE = 'check_violation';
                        -- (the two literals above are newline-separated, which SQL
                        -- treats as implicit concatenation into one string constant)
                    END IF;
                ELSE
                    IF NEW.seq <> head_seq + 1 OR NEW.prev_hash <> head_hash THEN
                        RAISE EXCEPTION
                            'audit_linkage_violation: seq/prev_hash does not extend'
                            ' the current head (expected seq=%, prev_hash=%)',
                            head_seq + 1, head_hash
                            USING ERRCODE = 'check_violation';
                    END IF;
                END IF;
                RETURN NEW;
            END;
            $fn$;
            """
        )
    )
    conn.execute(text(f"ALTER FUNCTION {SCHEMA}.audit_check_linkage() OWNER TO {OWNER_ROLE}"))
    conn.execute(
        text(
            f"""
            CREATE TRIGGER trg_entries_check_linkage
                BEFORE INSERT ON {SCHEMA}.entries
                FOR EACH ROW EXECUTE FUNCTION {SCHEMA}.audit_check_linkage();
            """
        )
    )
    # audit_app owns neither the table nor these functions and lacks TRIGGER privilege,
    # so it cannot ALTER TABLE ... DISABLE TRIGGER (spec.md sec 8).

    # --- Genesis row (spec.md sec 2.1 "Row 1 ... inserted by the migration as owner", sec 10) ---
    chain_id = "ps-demo-1"  # matches Settings.chain_id default; real value PS_AUDIT_CHAIN_ID
    event_id = "00000000-0000-0000-0000-000000000000"
    now = datetime.now(UTC)
    # 6 fractional digits, Z suffix (spec.md sec 4 timestamp format).
    occurred_at = now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "000Z"
    recorded_at = occurred_at

    genesis_payload = {"note": "genesis", "created_by": "migration"}
    content = {
        "v": 1,
        "chain_id": chain_id,
        "event_id": event_id,
        "event_type": "CHAIN_GENESIS",
        "event_version": 1,
        "producer": "migration",
        "occurred_at": occurred_at,
        "recorded_at": recorded_at,
        "actor": {"type": "system", "id": "migration", "auth_method": "none"},
        "request_id": "genesis",
        "trace_id": "genesis",
        "refs": {},
        "payload": genesis_payload,
    }
    canonical_bytes = _jcs_bytes(content)
    genesis_hash = _row_hash(GENESIS_PREV_HASH, canonical_bytes)

    conn.execute(
        text(
            f"""
            INSERT INTO {SCHEMA}.entries (
                seq, chain_id, event_id, event_type, event_version, producer,
                occurred_at, recorded_at, actor_type, actor_id, auth_method,
                request_id, trace_id, canonical, payload, prev_hash, row_hash
            ) VALUES (
                1, :chain_id, :event_id, 'CHAIN_GENESIS', 1, 'migration',
                :occurred_at, :recorded_at, 'system', 'migration', 'none',
                'genesis', 'genesis', :canonical, :payload, :prev_hash, :row_hash
            )
            """
        ),
        {
            "chain_id": chain_id,
            "event_id": event_id,
            "occurred_at": now,
            "recorded_at": now,
            "canonical": canonical_bytes.decode("utf-8"),
            "payload": json.dumps(genesis_payload),
            "prev_hash": GENESIS_PREV_HASH,
            "row_hash": genesis_hash,
        },
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text(f"DROP TRIGGER IF EXISTS trg_entries_check_linkage ON {SCHEMA}.entries"))
    conn.execute(text(f"DROP TRIGGER IF EXISTS trg_entries_reject_truncate ON {SCHEMA}.entries"))
    conn.execute(
        text(f"DROP TRIGGER IF EXISTS trg_entries_reject_update_delete ON {SCHEMA}.entries")
    )
    conn.execute(text(f"DROP FUNCTION IF EXISTS {SCHEMA}.audit_check_linkage()"))
    conn.execute(text(f"DROP FUNCTION IF EXISTS {SCHEMA}.audit_reject_mutation()"))
    op.drop_table("head_exports", schema=SCHEMA)
    op.drop_table("verify_runs", schema=SCHEMA)
    op.drop_table("entries", schema=SCHEMA)
    conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))
    # Roles are intentionally NOT dropped: they are cluster-wide objects that may be
    # referenced by other branches/tests; dropping them is a separate, human-reviewed step.
