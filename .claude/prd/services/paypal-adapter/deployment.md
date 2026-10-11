# paypal-adapter: deployment (zero cost)

Date: 2026-10-10. Labels: V verified, VC vendor claim, I inference/unverified. Sources: `architecture/deployment-zero-cost.md`, `ci-cd-and-repo-workflow.md`, ADR-004/005/009, `spec.md` sections 9 and 12. Env var NAMES only; no values anywhere.

## 1. Placement
| Profile | Where | Notes |
|---|---|---|
| B (submitted demo) | The `paypal` process, `hosts/paypal.py`, one Render free web service (host choice Proposed, ADR-005) | Runs ONLY paypal-adapter. ALWAYS reached over HTTP by other processes (never mounted in-process with `core`/`edge`/`ai`), so the PayPal secret exists only in this process env. |
| A (compose, judges/local + CI) | `services/paypal-adapter` container, own Dockerfile, own env file | Same code, same env names; PayPal vars only in this service's block of `docker-compose.yml`. Other services' blocks must not contain `PAYPAL_*` (CI env-manifest test). |
- Why a separate process in Profile B: the credential boundary is the reason the service exists (service-map). Co-locating it with `ai` is forbidden (LLM boundary).
- Cost: $0 and no card (Render without a payment method suspends instead of billing, V). Render free: 750 instance-hours per workspace (V) shared by `edge`, `core`, `ai`, `paypal`; sleeping consumes no hours (I). Do NOT run a 24/7 pinger on `paypal` (R11): only `edge` is pinged (UptimeRobot 5-min, V interval); `paypal` is woken by warm-up script and on first call. Cold wake ~1 min (V); callers use timeouts plus idempotent retry served by the ledger.
- Database: schema `paypal` on the shared Neon Postgres, role `paypal_app` with grants on that schema only (ADR-004). Do not use Render free Postgres (expires 30 days, V). Small pool; resume latency after DB pause unknown (I).
- Outbound: only `api-m.sandbox.paypal.com` (egress allowlist) and the audit push URL. No polling loops (Render "unusually high outbound traffic" suspension, V).

## 2. Secrets handling
Names only. Real values live in the Render environment (or secret file) of the `paypal` service, GitHub Actions secrets for the manual live job, and local untracked `.env`.
| Name | Where set | Notes |
|---|---|---|
| `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` | `paypal` service env only | secret never in DB, logs, ledger, image, compose file, CI logs. Repo `.env.example` has names + `changeme`-style placeholders. |
| `PS_CHECKOUT_TICKET_HMAC_KEY`, `PS_RESOLUTION_TICKET_HMAC_KEY`, `PS_CHECKOUT_TICKET_HMAC_KID`, `PS_RESOLUTION_TICKET_HMAC_KID` | `paypal` env (verifier holds both); each minter holds only its own | Minter env must not contain the other key (CI manifest test). |
| `PS_PAYPALADAPTER_DATABASE_URL` | `paypal` env | `paypal_app` role only. |
| `PS_PAYPALADAPTER_OUTBOX_FLUSH_SECRET` | `paypal` env + the scheduled flush workflow | |
| `PS_PAYPALADAPTER_INTERNAL_TRUSTED_ISSUERS` / `PS_PAYPALADAPTER_INTERNAL_JWKS_URL` | `paypal` env | public keys; not secret. |
- Env naming — RESOLVED: the user confirmed `PS_<SLUG>_*` as the strict project-wide convention on 2026-10-10. `PAYPAL_CLIENT_ID`/`PAYPAL_CLIENT_SECRET` are the ONE named exception, kept as-is rather than renamed to `PS_PAYPALADAPTER_*` — these are the exact names already used in the working, already-tested sandbox spike script and the real `.env` the user configured, so renaming would touch live, verified code for no functional benefit. Every other row in this table and file is now `PS_`-prefixed (`PS_PAYPALADAPTER_*` for this service's own vars; `PS_CHECKOUT_TICKET_HMAC_KEY`/`PS_RESOLUTION_TICKET_HMAC_KEY` named after the minting service, consumed here) — this pass is complete for paypal-adapter.
- Forbidden in this env (CI manifest test): `LLM_API_KEY`, session/CSRF/mandate/approval keys.
- Rules: gitleaks pre-commit + full-history CI (custom PayPal-secret-shaped rule, shape assumption I); `repr()` of config masks credentials; debug flag off in deployed env; rotate the sandbox secret before the repo goes public (it was used in spikes); if leaked, rotate at PayPal first, then purge.
- Fork PRs get no secrets; live-sandbox job runs only in the GitHub `sandbox` environment via `workflow_dispatch`.

## 3. Sandbox-only startup guard (refuse to start otherwise)
Order in `app.startup`; any failure logs a non-secret reason and `sys.exit(1)`:
1. `PS_PAYPALADAPTER_PAYPAL_MODE == "sandbox"`.
2. `PS_PAYPALADAPTER_PAYPAL_BASE_URL`: scheme `https`; host exactly `api-m.sandbox.paypal.com`; no userinfo, no port override, empty path.
3. HTTP client has fixed `base_url`, redirects disabled; request URLs built from fixed templates + ID regex.
4. `PS_PAYPALADAPTER_MONEY_ENABLED` parseable (unset/unparseable = frozen, fail closed, not a startup failure).
5. `/readyz` reports `sandbox_guard: pass`.
- Test: CI starts the app with each bad combination (production host, http, `PS_PAYPALADAPTER_PAYPAL_MODE=live`, userinfo, port, path) and asserts non-zero exit with no secret in output (maps to test-plan T-GUARD).
- Also: sandbox keys only; production credentials are never provisioned anywhere in this project.

## 4. Health
| Path | Auth | Behavior |
|---|---|---|
| `/healthz` | none | liveness; no DB, no PayPal call (cheap enough to survive being a wake-up probe) |
| `/readyz` | none | DB reachable, migration at expected head, config flags valid, `sandbox_guard: pass`; optional cached-token check (no new order). No secrets in body. |
| `/health` | none | alias for pingers (C8) |
- Warm-up script (`scripts/warmup`): parallel `/healthz` then `/readyz` with retries up to ~90 s (I), then one OAuth token fetch via the adapter readiness path (S01 equivalent, no order). Run ~30 min and ~10 min before any recording; the demo-readiness checklist also checks that token `expires_in` (~9 h, V) covers the recording window and that a 401 recovers.
- Token: memory only; cold start = fresh fetch; refresh single-flight; one retry on 401.

## 5. Return URL and webhook notes (Render)
- The adapter does NOT receive the PayPal return redirect. `checkout`/`web` own the return landing (U4); the adapter only validates the origin it is given against `PS_PAYPALADAPTER_PAYPAL_RETURN_URL_ALLOWED_ORIGINS`. Return URLs come from env, never hardcoded (preview deployments differ).
- Return landing should be a static `web` (Vercel) route that calls the API with retry, because an asleep `edge`/`core` makes the buyer wait ~1 min on a blank page (V). Ping/warm just before the approve click. Real return URL on the Render/Vercel host: untested end to end (I); test in week 1 (sprint task S1-04/S1-08 gate G1).
- Webhooks: default OFF (`PS_PAYPALADAPTER_WEBHOOK_ENABLED=false`). If enabled later, receiver `POST /v1/webhooks/paypal` needs a gateway pass-through decision (C9); it is a HINT only (record, emit `paypal.hint_received`, re-fetch before acting); signature verification and delivery to a sleeping host unverified (U3). Local dev: cloudflared quick tunnel (random URL each run, V) updating the allowed-origin env.
- `/mcp` and `/v1/*` are never routed by the public gateway. Judges reach MCP only through the optional read-only demo-inspector token (`PS_PAYPALADAPTER_DEMO_INSPECTOR_ENABLED=false` default) or a local compose run.

## 6. Deploy pipeline
- Render autodeploy OFF; deploy by Deploy Hook (secret in GitHub) from the pipeline so Alembic migrations (`paypal` schema) run first. Path-filtered CI on `services/paypal-adapter/**` (+ `libs/`, `contracts/`): ruff, types, pytest (doubles), gitleaks, pip-audit.
- After deploy: `scripts/warmup`, then smoke: `/readyz`, one token fetch, MCP `tools/list` as an allowed caller (8 tools for the union; filtered per caller), denied caller sees none. Smoke creates no money effect (no order) except the week-1/2 gate runs, which create a sandbox order deliberately.
- Scheduled workflows (Actions, not Render cron which is not free, V): outbox flush calling the flush endpoint with `PS_PAYPALADAPTER_OUTBOX_FLUSH_SECRET`; reconcile is driven by resolution's `/refunds/reconcile`.

## 7. Rollback
- Code: redeploy the previous image/commit via Deploy Hook (tag per release; Render keeps prior deploys, VC). Migrations are expand-only (add columns/tables, no destructive change in-sprint), so the previous code runs against the new schema. Never run a destructive migration after freeze (Nov 6).
- Config kill switches, fastest first: set `PS_PAYPALADAPTER_MONEY_ENABLED=false` (restart needed) or call operator freeze `POST /v1/control/freeze` (immediate, DB flag); either blocks all money tools while reads continue.
- Credential rollback: rotate the sandbox secret at PayPal, update only the `paypal` env, restart; in-memory token is dropped on restart.
- Ledger safety: rollback never deletes `call_ledger`/`refund_ledger`/`ticket_nonces`; in-flight `UNKNOWN` rows are reconciled by lookup after recovery, never re-sent under a new `request_id`.
- Fallback if the `paypal` process is unavailable on demo day: Profile A compose locally (documented); recorded video (Backup C) already shows the flow.

## 8. Open items (I)
- Render free limits and sleep timing re-verified Nov 1 (sprint S4-08 reminder); Neon connection limit and resume latency unknown; cold-start time of the `paypal` process unmeasured, report when measured; only ONE sponsor prize may be claimed (ADR-005).
