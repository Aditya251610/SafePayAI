# mandate: deployment (zero cost)

Labels V/VC/I. Free-tier facts come from `architecture/deployment-zero-cost.md` (read 2026-10-10; official pages cited there) and `architecture/overview.md` sec 8. Re-verify before 2026-11-01. Env var NAMES only; no values, no secrets.

## 1. Placement
| Profile | Where | Notes |
|---|---|---|
| B (demo, public link) | `core` process on one Render free web service (V: 750 instance-h/mo per workspace, spins down after 15 min idle, ~1 min wake), mounted by `hosts/core.py` with catalog, checkout, tracking, resolution, audit (ADR-005) | Checkout/resolution/shopping-agent calls to mandate are in-process (`PS_MANDATE_INPROCESS_TRANSPORT=true`) inside `core`; `ai` calls (shopping-agent -> mandate summary) are HTTP to `core`. Separate router, DB role and `aud=mandate` check still enforced in-process |
| A (target topology) | own container via `docker compose up` locally and in CI; optional one-time hosted rehearsal (cut-list item 2) | Same code; base URLs instead of in-process transport. State honestly: "same services, co-located for the free tier" |
- DB: one Postgres, Neon free preferred, POOLED endpoint for runtime (V per deployment doc: scale-to-zero after 5 min idle; 1 GB; compute-hour budget), schema `mandate`, role `svc_mandate` with grants only on that schema (ADR-004). Do NOT use Render free Postgres (V: expires 30 days after creation).
- Frontend `web` on Vercel (Hobby); no Python on Vercel.
- Not free / not used: Render cron/worker (V). The sweeper and outbox relay run as an in-process asyncio loop in `core` plus an external scheduled call to `POST /internal/sweep` and `POST /internal/outbox/flush` with `INTERNAL_TICK_SECRET` (GitHub Actions schedule or free pinger).
- Hours budget: only ONE always-on Render service fits 750 h (V). Pinger targets `edge` only; `core` is woken by the gateway fan-out health check and `scripts/warmup`.

## 2. Cold-start notes
- Wake cost: whole `core` process ~1 min on Render free (V). Mandate adds no extra cold hop in Profile B. In Profile A a sleeping mandate would add its own ~1 min (I: N services x ~1 min); that is why the demo uses B.
- Mandate boot work is local only: load config, load and validate HMAC keys, load trusted issuers (static map, no network), lazy DB pool. No outbound call at startup, no migration at startup (preferred), so wake time is not extended by mandate.
- First DB query after Neon idle suspend costs extra (resume latency unknown: I; commonly ~1-2 s, VC). `/readyz` pings DB; do not ping 24/7 (V math: 24/7 pings exhaust the compute budget in ~16 days). Ping only in review/recording windows.
- Critical click paths that touch mandate: sign (preview + POST), cart check (evaluate), confirm (reserve), return/capture (authorize-capture, commit). Web fires a warm-up GET through the gateway (`/readyz` fan-out) when the sign screen and the "Approve at PayPal" screen open, so `core` is awake before the click and before PayPal redirects back.
- Lock/timeouts must tolerate a just-woken DB: `PS_MANDATE_LOCK_TIMEOUT_MS` and `PS_MANDATE_STATEMENT_TIMEOUT_MS` are set above a normal resume delay; callers retry idempotently on 503 `LOCK_TIMEOUT` (never assume success).
- Reservation TTL (`PS_MANDATE_RESERVATION_TTL_SECONDS`) must comfortably exceed a cold return from PayPal; an expired reservation just forces re-reserve (spec Q11).
- Pre-recording: `scripts/warmup` hits all `/healthz` in parallel, `/readyz`, then sign + cart check + order create dry run; record within 10 min (deployment doc sec 4).

## 3. Env var names (values only in platform env)
Full table with meaning in `spec.md` sec 13. Grouped:
- Secrets (Render dashboard of the process mounting mandate, never in repo): `MANDATE_HMAC_KEY`, `MANDATE_HMAC_KEY_PREVIOUS`, `PS_MANDATE_MIGRATION_DATABASE_URL` (CI/deploy only, not in the runtime env), `INTERNAL_TICK_SECRET`. `PS_MANDATE_DATABASE_URL` contains a credential: treat as secret.
- Config: `PS_MANDATE_DATABASE_URL`, `PS_MANDATE_DB_POOL_SIZE`, `PS_MANDATE_HMAC_KEY_ID`, `PS_MANDATE_HMAC_KEY_ID_PREVIOUS`, `PS_MANDATE_INTERNAL_JWT_AUDIENCE`, `PS_MANDATE_TRUSTED_ISSUERS`, `PS_MANDATE_INTERNAL_JWKS_URL`, `PS_MANDATE_POLICY_VERSION`, `PS_MANDATE_CURRENCY`, `PS_MANDATE_MAX_TOTAL_CEILING_MINOR`, `PS_MANDATE_DEFAULT_MAX_QTY_PER_LINE`, `PS_MANDATE_MAX_QTY_PER_LINE_CEILING`, `PS_MANDATE_MAX_MERCHANTS`, `PS_MANDATE_INTENT_MAX_CHARS`, `PS_MANDATE_MIN_EXPIRY_SECONDS`, `PS_MANDATE_MAX_EXPIRY_SECONDS`, `PS_MANDATE_REFUND_CAP_CEILING_MINOR`, `PS_MANDATE_DELIVER_BY_DAYS_MIN`, `PS_MANDATE_DELIVER_BY_DAYS_MAX`, `PS_MANDATE_NONCE_TTL_SECONDS`, `PS_MANDATE_IDEMPOTENCY_TTL_SECONDS`, `PS_MANDATE_RESERVATION_TTL_SECONDS`, `PS_MANDATE_STUCK_CAPTURE_ALERT_SECONDS`, `PS_MANDATE_EXHAUST_DUST_MINOR`, `PS_MANDATE_LOCK_TIMEOUT_MS`, `PS_MANDATE_STATEMENT_TIMEOUT_MS`, `PS_MANDATE_ADVISORY_NEAR_CAP_PERCENT`, `PS_MANDATE_ADVISORY_EXPIRES_SOON_SECONDS`, `PS_MANDATE_SIGNING_ENABLED`, `PS_MANDATE_AUDIT_BASE_URL`, `PS_MANDATE_CHECKOUT_BASE_URL`, `PS_MANDATE_RESOLUTION_BASE_URL`, `PS_MANDATE_INPROCESS_TRANSPORT`, `PS_MANDATE_OUTBOX_FLUSH_INTERVAL_SECONDS`, `PS_MANDATE_LOG_LEVEL`.
- Repo: `.env.example` and `services/mandate/env.manifest` list names only. CI env-manifest test (T13/T14): mandate has none of `PAYPAL_*`, `LLM_*`, `APPROVAL_KEY`, `PS_CHECKOUT_TICKET_HMAC_KEY`, session/CSRF keys; no other service has `MANDATE_HMAC_KEY*`. gitleaks pre-commit and full-history CI scan.
- Note on `core` sharing: in Profile B all `core` services share one process environment (I: Render env vars are per service). Mandate code reads only its own names, and the manifest test is the guard; the key is therefore readable by other code in the same process. Disclose in the README ("co-located for the free tier"); Profile A isolates it.

## 4. Secrets handling
- Generate `MANDATE_HMAC_KEY` outside the repo with a CSPRNG (>= 256 bit), paste into the Render dashboard, never into chat, logs, docs, CI output, or `.env.example`. Different key per environment (local, staging, hosted demo). The agent writing code must not read or print `.env`.
- Boot check refuses to sign without a valid key (`/readyz` 503). Key bytes never in logs/health/errors (T26 log redaction test).
- Rotation drill once before submission (spec sec 10.3): add new current, move old to previous, redeploy, verify old mandates, run `scripts/mandate-keys-in-use`, drop previous. Record the dated result.
- Leaked key runbook: remove key (all rows signed with it fail closed), revoke affected demo mandates, reset demo (new ids), rotate; if re-attestation is built, follow spec sec 10.4. Never "fix" by editing stored rows.
- DB credentials: runtime role has no UPDATE/DELETE on immutable tables (spec sec 12 C4); the migration role is used only by CI/deploy.

## 5. Health, readiness, observability
- `GET /healthz`: liveness, no DB.
- `GET /readyz`: DB ping as `svc_mandate`, HMAC keys loaded and valid, migration revision equals code head, trusted issuers loaded. Failure = 503 so the health gate fails the deploy.
- Logs: JSON to stdout (Render logs; retention limited, I). Audit chain, not logs, is the record. Fields: `trace_id`, `request_id`, ids, outcome code. No `intent_text`, nonce, tokens, HMAC, keys.
- Stuck-capture signal: reservations in `CAPTURING`/`CAPTURE_UNKNOWN` older than `PS_MANDATE_STUCK_CAPTURE_ALERT_SECONDS` logged at WARN and counted in `/internal/sweep` output; checked in the pre-recording checklist.
- Monitoring: UptimeRobot on `edge` `/health/deep` (5-min; V interval) per deployment doc; mandate rides along via fan-out.

## 6. Migrations
- Alembic, per-service head, schema `mandate`. Order for a deploy: CI green -> run `alembic upgrade head` with `PS_MANDATE_MIGRATION_DATABASE_URL` from a GitHub Actions job (direct Neon endpoint, migration role) -> trigger Render deploy hook -> health gate. Fallback if the CI-run path is blocked: start command `alembic upgrade head && uvicorn ...` (costs cold-start time; Render free has no shell or pre-deploy job, V that one-off jobs/shell are unavailable; pre-deploy command on free: I).
- Migration 001 creates: tables (spec sec 2), CHECK constraints, immutability triggers (BEFORE UPDATE/DELETE raise on `mandates`, `revocations`, `nonces`, `nonce_uses`, `protection_grants`, and on term columns of `mandate_spend`), role grants (INSERT/SELECT on immutable tables; UPDATE only on `mandate_spend`, `spend_reservations`, `outbox`, `idempotency_keys`), indexes.
- Expand-and-contract; additive only during the demo window; no destructive migration after Oct 30 (sprint-plan: S4 hardening). Feature freeze Nov 6: no schema change after that (sprint-plan sec 5).
- Never ship `mandate.v2`/`canon.v2` or a new `render` version after freeze unless D1 is flipped to (b)/(c): old code cannot verify new versions and would fail closed (`MANDATE_INTEGRITY_FAILED`) on them, which makes rollback unsafe.
- Downgrade of the latest revision tested in CI. Test migrations on Neon with the real roles once in S1 (ADR-004 open item: INSERT/SELECT-only role and triggers on Neon, I).
- Seed: `scripts/seed_demo.py` calls the real API (preview + sign) so hashes, HMAC and audit entries are real; never SQL-insert mandates. Reset (`scripts/reset_demo.py`) uses the migration role to truncate mutable tables; mandates are new ids per reset, audit is never truncated (data-architecture sec 9).

## 7. CI/CD
- GitHub Actions path-filtered on `services/mandate/**`, `libs/**`, `contracts/**`: ruff, mypy/pyright (I), pytest (unit, contract, integration on Postgres service container), pip-audit, gitleaks, OpenAPI diff vs `contracts/openapi/mandate.json`, event schema check.
- Two parallel jobs (see test-plan sec 4): `profile-b` (in-process in `core`) and `profile-a` (compose). Both required; merge-blocking.
- Deploy: Render auto-deploy or deploy hook for `core`; Concurrency group per process; health gate `curl --retry` on `/healthz` and `/readyz` through the gateway (accounts for ~1 min wake); then smoke: sign -> evaluate -> reserve -> release on a throwaway mandate, then `scripts/warmup`.
- Money-path PRs (mandate included) run the chaos subset (test-strategy sec 8: C1-C5, C13, C19, C20 where applicable) plus the mandate concurrency suite.

## 8. Rollback
- Code: redeploy the previous commit SHA (`workflow_dispatch` with SHA input). Note the last known-good SHA in the README before recording.
- Schema: expand-and-contract so the previous code still runs on the new schema; do not drop columns in the last two weeks.
- Version caveat: rolling back past a commit that introduced a new `schema`/`render` version strands those rows (fail closed). Do not roll back across such a commit with live data; reset the demo instead.
- Data: the ledger is self-healing by idempotent retries: after a rollback run `POST /internal/sweep`, then checkout's `POST /internal/reconcile`; inspect reservations stuck in `CAPTURING`/`CAPTURE_UNKNOWN` by `GET /reservations/{id}` and resolve with checkout (no auto-release).
- Switches: `PS_MANDATE_SIGNING_ENABLED=false` stops new mandates while reads, evaluate, revoke and ledger calls continue. `PS_PAYPALADAPTER_MONEY_ENABLED=false` at paypal-adapter stops money (checkout then reports `MONEY_DISABLED`). Revoking a mandate is the per-mandate freeze.
- Demo fallback if mandate or DB is down during recording: pre-recorded clip of the sign/block/revoke scenes, labelled as recorded (honesty rule); never fake a hosted outcome.

## 9. Free-tier risks owned here
- Cold start on first sign/capture click (R3-type risk): warm-up + waking-server UX.
- Neon suspend/resume and pooled-connection quirks with row locks: transaction-scoped `FOR UPDATE` only; verify on Neon in S1 (I). If the pooled endpoint breaks lock semantics, use the direct endpoint for the mandate pool and note the connection limit (I, not on plan page).
- Render hour cap: no second 24/7 pinger.
- Env sharing inside `core` (sec 3 note).
