# audit

Append-only, hash-chained event log for SafePayAI. Records what the system did
(mandate, cart, order, tracking, case, offer, approval, refund, AI-call events) so a
buyer, reviewer, or judge can see the trail and run "verify chain". Not on the money
path and never decides anything -- see `.claude/prd/services/audit/prd.md`.

**Tamper-evident, not tamper-proof.** A database owner/superuser can rewrite history and
recompute the chain; verify would then pass. Only an external head anchor (`GET /head`,
committed to `docs/anchors.txt`) exposes a rewrite older than the anchor. See spec.md
sec 11 for the full honest-limits list. Never claim "immutable" or "tamper-proof".

Wave 5 status: real logic landed — JCS canonicalization, hash-chain append
(advisory-lock serialized, idempotent on `event_id`), `/verify` (gapless-seq + hash
recompute + anchor check), optional Ed25519 head signing, NDJSON export. 36 tests
(unit + integration against real Postgres).

## Run locally

```bash
uv run uvicorn app.main:app --reload
```

## Test

```bash
uv run pytest tests/unit -q            # no DB
uv run pytest tests/integration -q     # needs a real Postgres (docker compose up -d postgres)
```

## Migrate

```bash
uv run alembic upgrade head
```
