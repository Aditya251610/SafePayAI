# resolution: deployment (zero cost)

Labels V/VC/I. Free-tier facts come from `architecture/deployment-zero-cost.md` (read 2026-10-10; official pages cited there). Re-verify before 2026-11-01 (calendar reminder in sprint-plan S4-08). No secret values; names only.

## 1. Placement
| Profile | Where | Notes |
|---|---|---|
| B (demo, public link) | `core` process on Render free web service, mounted with mandate, catalog, tracking, checkout, audit (ADR-005). Render free: 750 instance-h/mo per workspace, sleeps after 15 min idle, ~1 min wake (V) | Calls to mandate, checkout, tracking are in-process ASGI (`PS_RESOLUTION_TRANSPORT=inproc`). Calls to `triage-ai` (in `ai`) and `paypal-adapter` (in `paypal`) stay HTTP. Max sync depth stays 3 (gateway -> resolution -> adapter) |
| A (target topology) | Own container via `docker compose up` locally and in CI L4; optional one-time hosted rehearsal (cut-list item 2) | Same code and image; base URLs instead of in-process transport; contract and L4 suites run against both (profile parity, test-strategy L2) |

- DB: one Neon Free Postgres (pooled endpoint), schema `resolution`, role `resolution_app` with grants only on that schema (ADR-004, V design; cross-schema SELECT denial is tested). Not Render free Postgres (expires at 30 days, V). Neon compute scales to zero after 5 min idle and 100 CU-h/month budget applies (V): DB pings only in review/recording windows.
- Schedulers: Render cron/worker are not free (V). Use (1) an in-process asyncio loop in `core` for reconcile (`PS_RESOLUTION_RECONCILE_INTERVAL_S`) and outbox relay, plus (2) a GitHub Actions scheduled call to `POST /internal/tick` with `PS_RESOLUTION_TICK_SECRET` as backup. Both are safe to overlap (row locks, `SKIP LOCKED`).
- The in-process loop dies when `core` sleeps. That is acceptable: all saga state is persisted (REQUESTED/SENT/UNKNOWN) and the first wake-up tick or request resumes it. No refund is ever started by a timer while frozen.
- Frontend: `web` on Vercel Hobby; no Python on Vercel (V).

## 2. Cold start notes
- Chain gateway (`edge`) -> `core` -> `paypal`/`ai` can stack ~1 min per sleeping hop (V per deployment doc); resolution accepts this and the warm-up script wakes all four in parallel.
- A buyer accept that lands on a cold `core` may time out at the gateway. Safe by design: the accept is idempotent, `Idempotency-Key` replays the stored response, and the saga is resumable. UI shows "waking server" and retries.
- Before a recording or judge window: `scripts/warmup` hits `/healthz` on all processes, then `/readyz` (DB + flag read), then runs a dry path to OFFERED on the seeded late order (S3-10), stopping before accept.
- The poller must not rely on the sleeping process: GitHub Actions `/internal/tick` every few minutes (interval unset; stay within Actions limits, I) and only during active windows to protect Neon CU-h.
- Neon resume latency on first query is unmeasured (I); measure in the S4 cold run.

## 3. Env var names (values only in platform env; none in repo or docs)
Prefix `PS_RESOLUTION_`. Names map from spec s14.

| Name | Kind | Note |
|---|---|---|
| `PS_RESOLUTION_DATABASE_URL` | secret | `resolution_app` role only |
| `PS_RESOLUTION_DB_POOL_SIZE` | config | small; Neon pooler |
| `PS_RESOLUTION_TRANSPORT` | config | `inproc` (Profile B) or `http` (Profile A) |
| `PS_RESOLUTION_SERVICE_ID` | config | `resolution` |
| `PS_RESOLUTION_INTERNAL_JWT_SIGNING_KEY`, `PS_RESOLUTION_INTERNAL_JWT_KID` | secret | tokens this service issues (scope `money.execute` to adapter) |
| `PS_RESOLUTION_INTERNAL_JWT_TRUSTED_ISSUERS` | config | static issuer/kid map, no runtime JWKS fetch |
| `PS_RESOLUTION_MANDATE_URL`, `_CHECKOUT_URL`, `_TRACKING_URL`, `_TRIAGE_AI_URL`, `_PAYPAL_ADAPTER_URL`, `_AUDIT_URL` | config | base URL or `inproc:` |
| `PS_RESOLUTION_APPROVAL_LINK_HMAC_KEY` | secret | approval token HMAC; distinct from every other key |
| `PS_RESOLUTION_APPROVAL_LINK_TTL_S`, `_APPROVAL_BASE_URL` | config | TTL default 24 h (I); public frontend origin |
| `PS_RESOLUTION_POLICY_VERSION`, `_POLICY_REFUND_CAP_MINOR`, `_POLICY_EXCLUDED_CATEGORIES`, `_POLICY_VELOCITY_MAX`, `_POLICY_VELOCITY_WINDOW_DAYS` | config | illustrative values, pinned version |
| `PS_RESOLUTION_TRIAGE_MIN_CONFIDENCE`, `_TRIAGE_TIMEOUT_S`, `_ADAPTER_TIMEOUT_S` | config | 0.7 is our heuristic (I); timeouts unset until S3 |
| `PS_RESOLUTION_PREAUTH_AUTO_EXECUTE` | config | tier 0 on/off |
| `PS_RESOLUTION_REFUNDS_FROZEN_DEFAULT` | config | must be `true`; used only to seed the flag row on first migration |
| `PS_RESOLUTION_FLAG_CACHE_TTL_S` | config | few seconds (I) |
| `PS_RESOLUTION_RECONCILE_INTERVAL_S`, `_REFUND_MIN_RECONCILE_AGE_S`, `_RECONCILE_MAX_ATTEMPTS` | config | unset until S3 |
| `PS_RESOLUTION_OUTBOX_RELAY_INTERVAL_S` | config | |
| `PS_RESOLUTION_HUMAN_REVIEW_SLA_TARGET_S` | config | demo target, unset by default |
| `PS_RESOLUTION_CASE_REPORT_MAX_CHARS` | config | untrusted text cap |
| `PS_RESOLUTION_TICK_SECRET` | secret | GitHub Actions `/internal/tick` |
| `PS_RESOLUTION_DEMO_MODE`, `_LOG_LEVEL` | config | SIMULATED CARRIER / sandbox labels |

- Forbidden in this service (CI test asserts absence from env manifest and image): `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, any LLM key, `MANDATE_HMAC_KEY`, `PS_CHECKOUT_TICKET_HMAC_KEY`. Resolution holds no PayPal credentials and makes no LLM call.
- In repo: `.env.example` and `services/resolution/env.manifest` list names only. gitleaks in pre-commit and CI; no secret in logs, docs or the frontend bundle.

## 4. Secrets handling
- Real values only in Render/Neon dashboards. Keys are purpose-separated (JWT signing, approval HMAC, tick secret differ). Rotation: change in dashboard, redeploy; rotating `PS_RESOLUTION_APPROVAL_LINK_HMAC_KEY` invalidates outstanding links, which then move to HUMAN_REVIEW on expiry, never deny.
- Logs: structured JSON with `trace_id`; never log tokens, approval URLs, `untrusted_text` bodies or DB URLs. Query strings stripped.
- `.env` is never read or printed by agents.

## 5. Health
- `GET /healthz` liveness, no DB. `GET /readyz` DB ping plus flag readable; flag unreadable reports `money_enabled=false` (service stays up, money gates closed). `/health` and `/health/deep` aliases (spec C8).
- Smoke after every deploy: `/healthz`, `/readyz`, then `GET /controls/refunds-frozen` returns a readable state, then the seeded late-order dry path to OFFERED.
- Deep checks touch Neon; run only in review/recording windows (24/7 pings exhaust CU-h in about 16 days, V math per deployment doc).

## 6. Migrations
- Alembic, schema `resolution` only, run by the pipeline before the new image starts (autodeploy OFF; deploy via hook after migrate, per CI/CD doc).
- Rules: expand-then-contract; additive only after the Day-8 contract freeze (ADR-008); no schema changes after feature freeze Nov 6.
- Migration 0001 creates all tables and the safety constraints: `UNIQUE(refund_attempts.case_id)`, `UNIQUE(invoice_id)`, `UNIQUE(request_id)`, partial unique on `refund_attempts(order_id)` for status in (REQUESTED, SENT, UNKNOWN, COMPLETED), `UNIQUE(approvals.tid)`, `UNIQUE(cases.order_id, cases.kind)`, `UNIQUE(inbox_dedupe.event_id)`, `UNIQUE(idempotency_keys.key, route)`; and seeds the `control_flags` row with `refunds_frozen = true`.
- Constraints are never dropped in a "contract" step; tests (RS-T40 range) assert they exist after every migration.
- Seed order for the demo: pre-made late order (S3-10), seeded with an idempotent script; demo reset restores it and must NOT unfreeze refunds.

## 7. REFUNDS_FROZEN: how it is stored and read
- Source of truth: one row in `resolution.control_flags` (`refunds_frozen bool NOT NULL`, `reason`, `set_by`, `set_at`, `epoch int`). Not an env var (an env var would need a redeploy and cannot be toggled by an operator in a demo).
- Default: the row is seeded `true`. Absent row, null, query error, timeout or stale-read failure = frozen (fail closed). `PS_RESOLUTION_REFUNDS_FROZEN_DEFAULT` only seeds the first row and cannot unfreeze an existing one.
- Read path: `FlagPort.is_frozen()` reads the row (cache at most `PS_RESOLUTION_FLAG_CACHE_TTL_S`; a toggle bumps `epoch` and invalidates the local cache). Read points: before offer auto-execution, check #1, immediately before the adapter call, and before any reconcile replay-send. Reconcile still reads (GET refund) while frozen.
- Write path: `PUT /controls/refunds-frozen`, operator role only, reason required to unfreeze, one transaction that updates the row, writes the outbox event `refund.freeze_changed`, and queues the adapter mirror push.
- Adapter mirror: resolution pushes the flag to `paypal-adapter` (`PUT /v1/controls/refunds-frozen`) with retry until ACKED; adapter fails closed if it has never received a value. `adapter_mirror: PENDING` is visible in the GET response; resolution's own gates already hold (spec C3). The adapter never reads the `resolution` schema (ADR-004).
- Effect: APPROVED items stay APPROVED (`queued_reason=REFUNDS_FROZEN`), not lost; after unfreeze they re-run all 9 checks. No state change on freeze block (spec check 1).
- Auto-trip hooks (thresholds unset, I) set the flag to true from reconcile mismatch; unfreeze is always manual.

## 8. Rollback
- Code: redeploy the previous image SHA via the deploy hook; the SHA of the last green deploy is noted in the sprint log before each deploy. No schema rollback after migration: additive migrations are forward-compatible with the previous image (expand-then-contract).
- If a deploy goes wrong while refunds are in flight: FIRST set `REFUNDS_FROZEN` (it is independent of the code version), then roll back, then run `POST /refunds/reconcile`, then unfreeze with a reason.
- Data: Neon PITR 6 h (V) for disaster recovery only; state is append-heavy (`case_transitions`, `outbox`), so prefer fix-forward. The audit chain is the evidence of record; never edit rows.
- Feature flags: `PS_RESOLUTION_PREAUTH_AUTO_EXECUTE` off and `refunds_frozen` on are the two safe-degraded modes (offers visible, nothing executes without a click, or nothing executes at all).
- After the Nov 6 freeze: config hotfixes and sev-1/sev-2 fixes only.

## 9. CI/CD
- GitHub Actions path-filtered on `services/resolution/**` and `libs/**`, with the single always-run `ci-gate` job (CI/CD doc). Stages: ruff + types, L1/L2/L3 on service Postgres, OpenAPI and event schema diff, gitleaks, build image, run side-by-side profile jobs (see test-plan s9), then deploy hook for Profile B after migrate.
- PRs touching resolution require the money-path chaos subset (C1-C5, C13, C19, C20).
