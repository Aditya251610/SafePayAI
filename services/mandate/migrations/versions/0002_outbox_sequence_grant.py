"""mandate: grant USAGE on the outbox bigserial sequence to svc_mandate

0001_baseline granted INSERT/SELECT/UPDATE on mandate.outbox but Postgres also
requires USAGE (and SELECT, for currval) on the backing sequence for a role to
insert rows with a serial/bigserial default - found via integration testing
(inserts failed with "permission denied for sequence outbox_seq_seq"). Additive
fix via a new migration per the convention of not editing an already-committed
migration (0001_baseline is in the Wave 4 scaffold commit).

Revision ID: 0002_outbox_sequence_grant
Revises: 0001_baseline
Create Date: 2026-10-11
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_outbox_sequence_grant"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "mandate"
RUNTIME_ROLE = "svc_mandate"


def upgrade() -> None:
    op.execute(
        f'GRANT USAGE, SELECT ON SEQUENCE "{SCHEMA}"."outbox_seq_seq" TO "{RUNTIME_ROLE}"'
    )


def downgrade() -> None:
    op.execute(
        f'REVOKE USAGE, SELECT ON SEQUENCE "{SCHEMA}"."outbox_seq_seq" FROM "{RUNTIME_ROLE}"'
    )
