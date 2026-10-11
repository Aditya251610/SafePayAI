# Data architecture (one Postgres, schema + role per service)

Labels: V verified (source cited), VC vendor claim, I inference/unverified. Date 2026-10-10. Implements ADR-003 (outbox) and ADR-004 (schema-per-service).

## 1. Verified Neon Free facts (and what is NOT known)

| Fact | Label | Source |
|---|---|---|
| 1 GB Postgres storage/project, 100 projects, 10 branches/project | V | https://neon.com/docs/introduction/plans |
| 100 CU-hours/project/month; autoscale max 2 CU | V | same |
| Scale-to-zero after 5 min idle; cannot be disabled on Free | V | same |
| 5 GB public egress/project/month | V | same |
| 6 h history/PITR window, 1 manual snapshot | V | same |
| Out of CU-hours/egress: compute suspended until next period. At storage cap: writes fail. None of these delete data | V | same |
| Cold start "typically a few hundred ms" plus network; app should raise connect timeout and retry with backoff | V | https://neon.com/docs/connect/connection-latency |
| PgBouncer transaction mode: max_client_conn 10,000; pool per (user, database) = 90% of max_connections; 0.25 CU = max_connections 104 (97 usable). Pool full: wait up to 120 s then error | V | https://neon.com/docs/connect/connection-pooling |
| Pooled mode: `SET search_path` does not persist; no LISTEN/NOTIFY, temp tables, session advisory locks, SQL-level PREPARE. Protocol-level prepared statements OK (PgBouncer 1.22+). Use direct connection for migrations and pg_dump | V | same |
| `CREATE ROLE` via SQL works; SQL-created roles are NOT neon_superuser; start with public-schema privileges only; 500 roles/branch; passwords need >= 60 bits entropy | V | https://neon.com/docs/manage/roles |
| Default CU on Free (0.25 vs other) and any inactivity-based project deletion policy | **unknown** (not on the pages read). Re-check https://neon.com/docs/introduction/plans and the console before submit. Treat "free project might be removed for inactivity" as possible (I) and keep the export in section 12 |
| INSERT/SELECT-only audit role and triggers work on Neon | I (standard Postgres; test in CI, section 11) |

Note: 100 CU-h is ~400 h at 0.25 CU (I, depends on actual CU). 24/7 pinging exhausts it in ~16 days. See section 9.

## 2. Topology

- One Neon project, one database `artiq`, branch `main` = demo. Branch `dev` (and per-PR branches within the 10 limit) for development (V limit; I usage).
- 10 service schemas + no schema for `web`. Each service connects only as its own role (`svc_<slug>`), with `ALTER ROLE ... SET search_path = <schema>` (needed because pooled mode drops `SET`; V) and fully qualified names in SQL as belt and braces.
- Two connection strings per service: `DATABASE_URL` (pooled endpoint, runtime) and `DATABASE_URL_DIRECT` (migrations only).
- No cross-schema SQL, views, or FKs. Cross-service references are plain id columns (`mandate_id`, `order_id`, `case_id`), validated by synchronous API calls, never by DB constraint. Cost: no referential integrity across services (accepted; reconciled by audit/verify scripts, section 13).

## 3. Schemas, tables, key columns

Types: ids are UUIDv7 (`uuid`, app-generated) unless noted. All tables have `created_at timestamptz default now()`. Money = `bigint` minor units + `currency char(3)`; never float/numeric-with-scale.

| Schema (owner) | Tables: key columns |
|---|---|
| `gateway` | `users(id, email uq, role)`, `sessions(id, user_id, expires_at)`, `signing_keys(kid, alg, status)` (metadata only, no secrets) |
| `mandate` | `mandates(id, buyer_id, status, max_total_minor, currency, merchant_allowlist jsonb, intent_text, expires_at, policy_version, nonce uq, terms_hash, hmac)` immutable terms; `revocations(mandate_id uq, at, reason)`; `nonces(nonce pk, mandate_id)`; `protection_terms(mandate_id pk, auto_refund_cap_minor, deliver_by_day)`; `idempotency_keys`; `outbox` |
| `catalog` | `merchants(id, name, settlement_ref)`, `items(sku pk, merchant_id, name, price_minor, currency, category)`, `categories`, `merchant_settlement_map`. Seed-only at runtime |
| `agent` | `proposal_log(id, mandate_id, prompt_hash, model_id, output jsonb, valid bool, latency_ms)` |
| `checkout` | `carts(id, mandate_id, total_minor)`, `cart_checks(cart_id, result, reasons)`, `orders(id, cart_id, mandate_id, status, paypal_request_id)`, `captures(capture_id pk, order_id, custom_id, invoice_id, amount_minor)`, `receipts`, `idempotency_keys`, `outbox` |
| `paypal` | `call_ledger(id, request_id uq, op, body_hash, status, response_id)`, `refund_ledger(id, refund_key uq, capture_id, invoice_id, amount_minor, paypal_refund_id, status)`. No secrets in DB (V per service-map) |
| `tracking` | `shipments(id, order_id uq, status, due_at)`, `shipment_events`, `demo_clock(id=1, now_override)`, `detector_runs`, `outbox` |
| `resolution` | `cases(id, order_id, mandate_id, kind, status, case_key uq)`, `case_transitions(case_id, from, to, at)`, `offers(id, case_id, amount_minor, proposal_hash, status)`, `approvals(id, proposal_id, token_hash uq, consumed_at)`, `policy_decisions`, `refund_attempts(id, case_id, request_id uq, amount_minor, status)`, `notifications`, `inbox`, `outbox` |
| `triage` | `triage_log(id, case_id, input_hash, model_id, output jsonb, valid bool)` |
| `audit` | `entries(seq bigint identity pk, prev_hash, hash, event_id uq, type, payload jsonb, ts)` |

## 4. Roles and grants matrix

Every role: `NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS`, login, own password in the service's platform env. `REVOKE ALL ON SCHEMA public FROM PUBLIC`; `REVOKE CONNECT`-style isolation is not needed because schema USAGE is the barrier (I: also revoke default PUBLIC table privileges).

| Role | Own schema | Other schemas | Notes |
|---|---|---|---|
| `mig_<slug>` (migration owner, one per schema; used only in deploy step, direct URL) | owner, DDL | none | tables are owned by it; runtime role never owns tables |
| `svc_<slug>` (runtime) | USAGE; SELECT/INSERT/UPDATE (DELETE only on idempotency/outbox sweep tables) | no USAGE, no grants | cannot read any other schema |
| `svc_catalog` | SELECT only | none | catalog is read-only at runtime; seeded by `mig_catalog` |
| `svc_mandate` on `mandates`, `revocations`, `nonces` | INSERT/SELECT only on `mandates`, `nonces` (no UPDATE: terms immutable); status changes via `revocations` row | none | enforces immutability |
| `svc_audit` | INSERT, SELECT on `entries`; USAGE on its identity sequence; no UPDATE/DELETE/TRUNCATE | none | plus trigger `BEFORE UPDATE OR DELETE OR TRUNCATE` raising an exception (defense in depth; owner `mig_audit` could bypass, so owner credential is never deployed at runtime) |
| `ops_readonly` | none | SELECT on all schemas except `gateway.sessions` | for a human/dashboards; not used by services |
| `ops_admin` | the Neon-console owner role | all | local machine only, never in a service env |

Audit can be written to only via `audit` service `POST /append` (internal token). Other services never connect to `audit` schema. Hash-chain append is serialized with a single-row lock in the same transaction (`SELECT ... FOR UPDATE` on last entry, or `pg_advisory_xact_lock`, which is transaction-scoped and allowed in pooled mode; V that only session-level locks are unsupported).

Grants are emitted by each service's Alembic baseline migration through a shared `libs/db_grants` helper, plus a CI test (section 11) asserting the matrix (`has_schema_privilege`, `has_table_privilege`).

## 5. Money

- Integer minor units (`bigint`) with `currency`; `CHECK (amount_minor > 0)`, `CHECK (currency ~ '^[A-Z]{3}$')`. Conversion to PayPal decimal strings happens only in `paypal-adapter` (single place; round-trip unit tests).
- Cart total includes fees (per context brief). Refund amount never exceeds `captures.amount_minor` minus sum of completed `refund_ledger.amount_minor` (checked in resolution check list AND PayPal returns 422 REFUND_AMOUNT_EXCEEDED on real over-refund, V per brief).

## 6. Uniqueness and idempotency constraints

| Invariant | Constraint |
|---|---|
| One refund per case | `resolution.refund_attempts`: partial unique index `ON (case_id) WHERE status IN ('REQUESTED','UNKNOWN','COMPLETED')`. Failed attempts may be followed by a human-approved new offer (new case_id or explicit retry flag; decision for resolution owner) |
| One invoice_id per refund | `paypal.refund_ledger UNIQUE(invoice_id)`; PayPal also rejects duplicate invoice_id with 422 DUPLICATE_INVOICE_ID (V per brief) |
| One PayPal-Request-Id per logical call | `paypal.call_ledger UNIQUE(request_id)`; `refund_attempts UNIQUE(request_id)`; request_id row is committed BEFORE the external call (rule R4) |
| One approval per proposal | `resolution.approvals`: `UNIQUE(proposal_id)` and `UNIQUE(token_hash)`; consumption via `UPDATE ... SET consumed_at=now() WHERE id=$1 AND consumed_at IS NULL` (rowcount 1 or reject). Token stored hashed |
| Unique mandate nonce | `mandate.mandates UNIQUE(nonce)` and `nonces(nonce PK)` |
| One case per shipment+kind | `resolution.cases UNIQUE(case_key)` where `case_key = order_id:kind`; tracking `shipment_events UNIQUE(shipment_id, kind)` |
| One capture per order | `checkout.captures UNIQUE(order_id)`, `UNIQUE(invoice_id)` |
| One mandate revocation | `mandate.revocations UNIQUE(mandate_id)` |
| Idempotent public POST | `idempotency_keys(key, scope, request_hash, response, created_at) UNIQUE(scope, key)` in mandate/checkout/resolution. Same key + different hash = 409 |
| Audit dedupe | `audit.entries UNIQUE(event_id)`; append is `INSERT ... ON CONFLICT DO NOTHING` |
| Valid state transitions | `case_transitions` written in the same transaction as the `cases.status` update; `CHECK` enumerating statuses |

## 7. Outbox and inbox

Outbox (in mandate, checkout, tracking, resolution; paypal may add if it emits): `outbox(seq bigserial pk, event_id uuid uq, type, version, aggregate_id, payload jsonb, trace_id, created_at, delivered_to jsonb default '{}', attempts int, next_attempt_at)`. Event row inserted in the same transaction as the state change (ADR-003). Relay: in-process asyncio loop plus `POST /internal/outbox/flush` for external cron; selects due rows with `FOR UPDATE SKIP LOCKED` inside a short transaction, delivers over HTTP outside the transaction, then marks per-subscriber delivery. Pull catch-up `GET /internal/outbox?after=seq`. Retention: delete delivered rows older than 7 days (keeps 1 GB budget; I).

Inbox (consumers that act, i.e. resolution and checkout; audit uses `event_id` unique instead): `inbox(event_id uuid pk, type, received_at, processed_at)`. Handler does `INSERT ... ON CONFLICT DO NOTHING`; if no row inserted, ack and skip. Insert and effect in one transaction.

At-least-once only; consumers dedupe (ADR-003).

## 8. Migrations strategy

- Alembic per schema: `services/<slug>/migrations/`, `version_table_schema=<schema>` so each service has its own `alembic_version`. Each env.py sets `include_schemas=False` for foreign schemas and refuses to touch others.
- Runs as `mig_<slug>` over the direct URL (V: use direct connection for migrations) as a deploy step before the new service version takes traffic (Render pre-deploy command or CI job; I per host). Idempotent, advisory-lock guarded (`pg_advisory_lock` on the direct session, which is fine on a non-pooled connection).
- Expand/contract: release N expands (add nullable column/table, dual-write if needed), release N+1 contracts. Rule: running code N-1 must work against schema N. Index builds `CREATE INDEX CONCURRENTLY` (needs `autocommit` block in Alembic); for demo-size tables plain index is harmless, but keep the habit.
- Every revision has `downgrade()` except destructive contract steps, which are documented as forward-only with an export taken first.
- CI: `alembic upgrade head` on empty DB, `downgrade base`, upgrade again; plus grants-matrix test.
- Freeze: no schema change after 2026-11-08 (submit target 11-10); migrations after freeze need explicit sign-off.

## 9. Connections, cold start, compute hours

Risks and mitigations:

| Risk | Mitigation |
|---|---|
| Scale-to-zero cold start on first query (a few hundred ms, V; seconds if network-bound, I) stacks with app cold start | Connect timeout 10 s, 3 retries with exponential backoff + jitter on connect errors only; retry queries only if idempotent; pool `pre_ping` on checkout; `/health/deep` uses the same path |
| Connection exhaustion: 11 services x pool | Use the pooled endpoint (V: 10,000 client conns). SQLAlchemy `pool_size=2, max_overflow=3` per instance (I), `pool_recycle=300`. Direct connections only for migrations. Per-role pools are separate in PgBouncer but share max_connections (V) |
| Pooled-mode incompatibilities | `search_path` via `ALTER ROLE`; no LISTEN/NOTIFY, no temp tables, no session advisory locks (use `pg_advisory_xact_lock`). asyncpg/psycopg: prepared-statement caching only with protocol-level support (PgBouncer 1.22+ V); if errors appear set `statement_cache_size=0` (I) |
| Pool-full wait 120 s (V) | Set `command_timeout` 15 s and statement_timeout 10 s per role (`ALTER ROLE ... SET statement_timeout`) |
| Compute-hour budget (100 CU-h, V) | Policy: **sleep by default, warm only in windows.** Dev/CI use branch `dev`, not `main`. Do NOT run a 24/7 DB pinger. Pinger hits service `/health` (no DB) normally; `/health/deep` (touches DB) only in scheduled review windows (see below). Outbox relay must not poll the DB when idle: relay loop runs after a write (triggered), plus cron flush at low frequency. An in-process poll every few seconds would keep the compute awake 24/7 and burn the budget (I, inferred from 5 min suspend V) |
| Budget math (I from V figures) | 100 CU-h / 0.25 CU = 400 runtime hours (V plan figure, CU size assumed) vs ~730 h in a month. Conclusion: 24/7 not affordable at 0.25 CU; ~13 h/day average is the ceiling. Autoscaling above 0.25 CU shortens this |
| Review-window plan (I) | Judging 12-01..12-15 = 15 days. Budget ~400 h/month at 0.25 CU. Keep warm 08:00-22:00 UTC daily via pinger (14 h x 15 d = 210 h) and let it sleep overnight, leaving headroom for demo traffic and the monthly reset. Check console usage weekly. If minimum CU is larger than 0.25, recompute: hours = 100 / CU |
| Hard stop at limit | Compute suspends until period resets (V). Mitigation: usage alert check in the weekly routine; fallback in section 12 |

## 10. Seed and reset for demo

- Seeds are Alembic data migrations for `catalog` only (12 items, 3 merchants). Demo users and one demo mandate via `scripts/seed_demo.py` calling service APIs (not direct SQL), so hashes, HMAC, and audit entries are real.
- `scripts/reset_demo.py` (guarded by `DEMO_RESET_ENABLED` and an operator token, never exposed via the gateway publicly): per service, `TRUNCATE` mutable tables as `mig_<slug>` over the direct URL, EXCEPT `audit.entries`, which is never truncated (the runtime role cannot; reset instead starts a new demo "epoch" row/marker, or recreates the schema via `mig_audit` in dev only). Production demo reset = new mandate/order ids, not wiping audit, so the chain stays verifiable.
- Reset order: tracking, resolution, checkout, mandate, agent, triage, paypal ledgers (keep PayPal ledgers if the same sandbox capture ids remain referenced; I). Then reseed; target < 30 s.
- Time travel is via `tracking.demo_clock` only; no DB clock tricks.

## 11. Testing and local

- **Profile A local:** `docker compose` with one `postgres:16` (match Neon's major version; check console, I), init script creating the schemas and roles from the same `libs/db_grants` code as production, so grants are tested locally. Compose uses a plain (non-pooled) URL for migrations and optionally a `pgbouncer` container in transaction mode (V behaviors above) to catch pooled-mode bugs (`edoburu/pgbouncer` or equivalent; I).
- **Test database strategy:** one test Postgres (compose or CI service container). Per test run create a unique schema set `t_<runid>_<slug>` (or one database `test_<runid>`), run Alembic with `version_table_schema` and a schema-name override, run tests, `DROP SCHEMA ... CASCADE` at teardown. Parallel workers get `<runid>_<worker>`. Roles are created once per cluster; grants applied per ephemeral schema. Never run tests against the Neon `main` branch; CI on Neon uses a throwaway branch (V: 10-branch limit; delete after run).
- Mandatory DB tests: grants matrix; audit UPDATE/DELETE/TRUNCATE rejected for `svc_audit` and by trigger; unique-refund, unique-invoice, single-use approval, nonce uniqueness, concurrent double-consume of an approval (2 tasks, exactly one wins); outbox/inbox duplicate delivery; money round-trip.

## 12. Backup, export, and DB expiry/pause contingency

Neon Free gives only 6 h PITR and 1 snapshot (V), so own the backups:

- Nightly GitHub Actions job (cron): `pg_dump` over the direct URL (schema + data, `--format=custom`) to a workflow artifact (retention 30 d; I) and a weekly encrypted copy in a private repo release or local disk. Secrets are the `ops_readonly` URL (not owner) where possible. A dump wakes the compute briefly; run once/day (cost trivial, I).
- One-time snapshot before submit (11-09) and before judging (11-30), using Neon's manual snapshot (V, 1 allowed) plus pg_dump.
- If compute is suspended for quota (V: data kept, compute off until next period): demo keeps loading but fails on DB; the app must show a clear "demo database is resting" page (gateway maps DB-unavailable to 503 with that message). Prepare video + screenshots as the judging fallback (video is a submission requirement anyway).
- If the project is deleted/expired/paused before 12-21 (policy unknown, section 1): (1) restore latest dump into a new Neon project (free, 100 projects V) or Supabase Free as secondary (500 MB, pauses after 1 week idle, V per deployment doc); (2) swap `DATABASE_URL`s in the host envs (documented runbook, < 15 min); (3) re-run `alembic upgrade head` + `seed_demo.py` if no dump is usable. Because `seed_demo` uses the APIs, a fresh DB is always recoverable; only the old audit history is lost.
- Pre-flight checklist at 11-28 and 12-01: console shows project active, CU-h remaining, storage < 50%, last dump < 24 h old, `/health/deep` green, `GET /audit/verify` passes.
- README run instructions (hackathon requirement) must work with local compose only, so judges are never blocked by the hosted DB.

## 13. Index and performance checklist (demo load only)

Demo load (I): one or two concurrent users, < 50 orders, < 2 000 rows per table, < 50 MB total. Do not over-engineer; verify with EXPLAIN on the few hot paths and do not tune beyond that.

- [ ] Every id column used for lookups from another service has an index (they have no FK, so nothing is auto-indexed): `orders(mandate_id)`, `captures(order_id)` (unique), `cases(order_id)`, `cases(mandate_id)`, `cases(status)`, `offers(case_id)`, `approvals(proposal_id)` (unique), `shipments(order_id)` (unique), `refund_attempts(case_id)`, `case_transitions(case_id, at)`, `proposal_log(mandate_id)`.
- [ ] Unique constraints from section 6 present (they are also the hot lookup indexes).
- [ ] Outbox: partial index `ON outbox(next_attempt_at) WHERE delivered_to_all = false` (add a `done boolean`), so the relay scan stays O(pending).
- [ ] Audit: `entries(seq)` PK serves tail read for chain append; `GET /entries` paginates by `seq`, `limit <= 100`.
- [ ] No `SELECT *` in service code; list endpoints paginate (limit <= 100).
- [ ] `statement_timeout` and `idle_in_transaction_session_timeout` set per role.
- [ ] No transaction held open across an HTTP call (outbox delivery and PayPal calls happen outside transactions; money state is committed BEFORE the external call, R4).
- [ ] No N+1 across services: gateway BFF issues parallel calls; within a service use joins or `WHERE id = ANY($1)`.
- [ ] Run `EXPLAIN (ANALYZE, BUFFERS)` once on: mandate evaluate read, case list by status, outbox flush select, audit append. Seq scans on tables this small are acceptable; just ensure no unbounded sort.
- [ ] Enable `pg_stat_statements` if available on Neon (I, check) for one pass before submit; otherwise log slow queries > 200 ms in the app.
- [ ] Storage guard: outbox/idempotency sweeps; `triage_log`/`proposal_log` store hashes and bounded output (<= 8 KB) to stay far below 1 GB.

## 14. Open items for owners

1. Confirm Neon default CU and whether inactivity deletion exists (unknown above).
2. Test the INSERT/SELECT-only `svc_audit` role + trigger on Neon (I).
3. Decide retry-after-failure semantics for "one refund per case" (section 6).
4. Confirm host pre-deploy migration hook (Render) or use a CI deploy step.
5. Confirm driver (asyncpg vs psycopg3) behavior behind PgBouncer 1.22+.
