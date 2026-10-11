# audit - deployment

Labels: V verified, VC vendor claim, I inference/unverified. Date 2026-10-10. Sources: deployment-zero-cost.md, data-architecture.md, sprint-plan.md, ADR-004/005. Monorepo: this service lives at `services/audit/` in the single public repo (ADR-009); no separate-repo assumption anywhere in prior audit docs, so no conflict to flag here.

## 1. Placement (zero-cost)
- DB: Neon Free, schema `audit`, shared single Postgres project with all other services (ADR-004). (V data-architecture.md sec 1-2)
- Process: Profile B default - co-located inside `core` process with mandate/checkout/resolution/tracking (service-map, spec.md sec 1). Profile A (own container) exists for local compose and as the architecture-honest fallback.
- No separate compute decision needed beyond the shared `core` host (Render free web service). Audit adds no new Render/Vercel footprint.

## 2. Connection limits (Neon Free, V per data-architecture.md sec 1)
- Pooled endpoint: PgBouncer transaction mode, `max_client_conn` 10,000; per (user, database) pool = 90% of `max_connections`; at 0.25 CU, `max_connections` 104 (~97 usable) - shared across ALL 10 services' roles, not audit-only.
- `PS_AUDIT_DATABASE_URL` (runtime, `audit_app` role) uses the pooled endpoint; `PS_AUDIT_DB_POOL_MAX` kept small (config, value I - not set) since the chain append path is already serialized by the advisory lock (spec.md sec 3) and does not benefit from a large pool.
- Pooled-mode constraints that apply to audit: no session-level advisory locks (use `pg_advisory_xact_lock`, transaction-scoped - V, confirmed safe under PgBouncer transaction mode in data-architecture.md sec 1); no `LISTEN/NOTIFY`, no temp tables, no session-level `PREPARE`; `prepare_threshold=None` in psycopg (protocol-level prepared statements only, needs PgBouncer >=1.22, VC).
- `PS_AUDIT_MIGRATE_DATABASE_URL` (CI-only, `audit_owner`/`mig_audit`) uses the DIRECT endpoint, never pooled - required for migrations and `pg_advisory_lock` session-level locking during Alembic (data-architecture.md sec 8). Startup check refuses to boot if both URLs are set in the same env (spec.md sec 8).
- Pool-full wait is 120 s before Neon errors (V); audit sets `statement_timeout`/`command_timeout` well under that per data-architecture.md sec 9 guidance.

## 3. Scale-to-zero cold-start risk
- Neon Free scales to zero after 5 min idle, cannot be disabled on Free (V, deployment-zero-cost.md sec 1 / data-architecture.md sec 1). Resume latency commonly "a few hundred ms" per Neon's own connection-latency doc (V) but network/app-level cold start can add seconds (I).
- Audit-specific mitigation already in spec: `/healthz` NEVER touches the DB (REQ-AU-050, api.md sec 6) so the keep-warm pinger does not force the DB awake 24/7 and burn CU-hours. `/readyz` does touch the DB (`SELECT 1`, genesis check) but is for warm-up scripts, not a 5-min pinger.
- Append and verify calls after idle absorb the cold start as normal connect latency (retry/backoff on connect errors only, per data-architecture.md sec 9); producers' outbox retries absorb a 503 `DB_UNAVAILABLE`/`CHAIN_BUSY` from audit during this window (api.md sec 1).
- Risk specific to audit: a judge clicking "verify chain" right after idle sees a slower-than-usual response, not a failure, since `/verify` streams in short per-chunk read txns (spec.md sec 7) that each pay a (smaller, already-resumed) cold-start cost only on the first chunk.

## 4. Env names (names only, no values - full list is spec.md sec 15, repeated here for the deployment doc)
| env | purpose |
|---|---|
| `PS_AUDIT_DATABASE_URL` | pooled Neon URL, `audit_app` role (platform secret) |
| `PS_AUDIT_MIGRATE_DATABASE_URL` | CI only; direct URL, `audit_owner`/`mig_audit`; refused if present at runtime |
| `PS_AUDIT_DB_POOL_MAX` | small pool size |
| `PS_AUDIT_CHAIN_ID` | constant chain identifier (e.g. `ps-demo-1`) |
| `PS_AUDIT_ENV` | `dev\|ci\|demo\|prod`; guards the tamper script from running on prod |
| `PS_AUDIT_TRUSTED_ISSUERS` | static trusted issuer public keys map (no network JWKS fetch) |
| `PS_AUDIT_EMISSION_ALLOWLIST_PATH` | file path of `(producer, event_type, actor_type)` allowlist |
| `PS_AUDIT_HEAD_SIGNING_KEY` | Ed25519 private key (secret, optional P1) |
| `PS_AUDIT_HEAD_SIGNING_KEY_ID` | key id exposed in head export |
| `PS_AUDIT_VERIFY_CHUNK` | verify keyset chunk size |
| `PS_AUDIT_APPEND_MAX_RETRIES` | bounded retry on lock/linkage errors |
| `PS_AUDIT_PAGE_MAX` | max grid page size |
| `PS_AUDIT_INTERNAL_AUDIENCE` | expected `aud` claim (`audit`) |
| `PS_AUDIT_LOG_LEVEL` | logging |
Secret hygiene (no values ever in repo or this doc): `.env.example` carries names only; CI env-manifest test asserts `PAYPAL_*` and `LLM_API_KEY` do NOT exist in audit's env (service-map / auth-gateway credential-isolation rule).

## 5. Health
- `GET /healthz`: no DB call, liveness only (REQ-AU-050). Safe for 5-min keep-warm pingers (UptimeRobot/cron-job.org) without burning Neon CU-hours.
- `GET /readyz`: `SELECT 1`, genesis-row present (cached after first success), trusted issuers loaded; 503 with flags if not ready. Used by `scripts/warmup` and deploy-time health gate, not by frequent pingers (data-architecture.md sec 9 "sleep by default, warm only in windows" policy applies to audit too).
- Deploy ritual (sprint-plan.md sec 0): CI green -> auto-deploy to Profile B -> health gate `curl --retry` on `/healthz` (accounts for ~1 min Render wake, V) -> smoke test -> `scripts/warmup`.

## 6. Migrations
- Alembic, own schema `audit`, own `alembic_version` table scoped to schema `audit` (`version_table_schema=audit`, data-architecture.md sec 8).
- Run as `mig_audit` (= `audit_owner`) over the DIRECT Neon endpoint, as a deploy pre-step before new code takes traffic (Render pre-deploy command or CI job - exact host hook I, per data-architecture.md sec 8).
- One dedicated Alembic revision creates: schema, `audit_owner`/`audit_app` roles, grants (`REVOKE ALL ... FROM PUBLIC` then explicit `GRANT`), the three BEFORE triggers (UPDATE/DELETE/TRUNCATE reject, BEFORE INSERT linkage check), and the genesis row (spec.md sec 2.1, sec 8).
- Idempotent, advisory-lock guarded (`pg_advisory_lock` on the direct, non-pooled session - fine outside PgBouncer).
- Expand/contract rule applies (data-architecture.md sec 8): running code N-1 must work against schema N. Audit's append-only nature means contract-style migrations (dropping/narrowing a column) are effectively forward-only once rows exist, since nothing may be rewritten; any such change needs a new chain generation (spec.md sec 13), not an in-place migration.
- CI test: `alembic upgrade head` on empty DB, `downgrade base`, upgrade again, plus the grants-matrix test (data-architecture.md sec 8, 11).
- Schema freeze: no schema change after 2026-11-08 per sprint-plan.md sec 8 (submit target 2026-11-10); any post-freeze migration needs explicit human sign-off.

## 7. Backup / export
- Neon Free gives only 6 h PITR and 1 manual snapshot (V, data-architecture.md sec 1) - not a backup of record for a log that can never be rewritten to recover lost rows.
- Own backups (data-architecture.md sec 12, spec.md sec 13):
  - `GET /export?from_seq=&to_seq=` streams NDJSON of full rows (`canonical` + hashes); reviewer/operator only; no secrets by construction.
  - Nightly GitHub Actions job: `pg_dump` of the `audit` schema over the direct URL to a workflow artifact (retention ~30 d, I) plus a weekly encrypted copy kept outside the repo.
  - One-time manual Neon snapshot + `pg_dump` before submit (2026-11-09) and again before the judging window (2026-11-30, per data-architecture.md sec 12).
- Audit-specific rule: `scripts/reset_demo.py` MUST NEVER truncate `audit.entries` (data-architecture.md sec 10) - the chain is the one thing a demo reset does not wipe; a reset starts a new "epoch" marker instead, never a `TRUNCATE`, which the `audit_app` role cannot do anyway (no DELETE/TRUNCATE grant).

## 8. If Neon pauses/expires before Dec 21 judging
- Known facts (V, data-architecture.md sec 1): at CU-hour or egress limit, compute is suspended until next period - data is NOT deleted. At storage cap, writes fail - data is NOT deleted. Whether an inactive Free project can be deleted/expired outright is **unknown** (not documented on the pages read); treat as possible (I) and plan as if it could happen.
- If compute is merely suspended (quota exhaustion): the app loads but DB calls fail; gateway maps this to a 503 "demo database is resting" page (data-architecture.md sec 12) rather than a raw error. No audit data is lost; it resumes next billing period or after a manual bump.
- If the project is deleted/expired/paused outright before judging (worst case, policy unknown):
  1. Restore the latest `pg_dump` into a new Neon project (free, up to 100 projects/account - V) or Supabase Free as secondary (pauses after 1 week idle - V, not for primary use).
  2. Swap `PS_AUDIT_DATABASE_URL`/`PS_AUDIT_MIGRATE_DATABASE_URL` in the platform env (documented runbook target: < 15 min).
  3. Re-run `alembic upgrade head` (recreates schema/roles/triggers/genesis) then `scripts/seed_demo.py` (calls real service APIs, so hashes/HMAC/audit entries are genuine, not DB-inserted fakes).
  4. Honest cost: a fresh DB means the OLD audit history (and any pre-restore head anchors) is lost unless the NDJSON export/dump from step 1 is replayed first into the new project before re-seeding. If a recent dump exists, restore it first; only fall back to a bare reseed if no usable dump exists.
- Pre-flight checklist (data-architecture.md sec 12), carried over for audit specifically: at 2026-11-28 and 2026-12-01, confirm Neon console shows project active, CU-h remaining, storage < 50%, last dump < 24 h old, `GET /audit/verify` passes, `GET /audit/head` paste string matches the one committed in `docs/anchors.txt`.
- Calendar reminder (sprint-plan.md sec 6): keep demo alive Nov 13 - Dec 21 with a scheduled smoke every 6 h hitting `/healthz`, `/readyz`, and `/verify`; re-check Render-hours/Neon-CUh/LLM quota resets; this is the mechanism that would surface a Neon pause/expiry early, before judging day.

## 9. Rollback
- Code rollback: redeploy the previous tagged commit/image on the `core` host (Render auto-deploy from a pinned SHA via `workflow_dispatch`, per deployment-zero-cost.md sec 9); audit's own router/schema versioning (`canonical.v`, `event_version`) means an older binary can still read newer rows written by a short-lived bad deploy, as long as no destructive migration ran.
- Schema rollback: every Alembic revision has `downgrade()` EXCEPT destructive contract steps (none expected for an append-only table in v1); any added-but-unused column can be dropped forward-safely post-freeze if truly needed, but per the honest-limits section of spec.md, no migration may ever `UPDATE`/`DELETE` existing chain rows - a bad migration that corrupted data is fixed by restoring the last good `pg_dump`/export, not by a destructive "undo" migration.
- Role/grant rollback: grants are emitted by the same `libs/db_grants` helper used elsewhere (data-architecture.md sec 4) and are idempotent, so re-running the grants step safely reverts an accidental manual `GRANT`/`REVOKE` drift.
- Bad append-logic deploy (e.g. a canonicalization bug that would write wrong hashes): the fix is to roll back the service binary before more bad rows are appended; already-written bad rows cannot be edited (by design) - the honest fallback is a new chain generation (spec.md sec 13: export, anchor final head of generation N, start generation N+1), not a live fix of generation N. This is a known limitation, not a deployment gap, and is explicitly out of scope for v1 (spec.md sec 13).
- Kill-switch note: audit itself has no write access outside its schema and cannot trip `REFUNDS_FROZEN` (spec.md conflict C3/C9) - a rollback of audit never needs to coordinate with the money-path kill-switch, simplifying the rollback blast radius to this schema only.
