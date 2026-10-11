# api-gateway: deployment (zero cost)

Labels: V verified (official page read, see deployment-zero-cost.md for URLs), VC vendor/secondary, I inference. Free-tier limits change: re-check on Nov 1 (sprint S4-08). Sources: architecture/deployment-zero-cost.md, adr.md (ADR-004/005/009), service-map.md, agent-context-map.md, spec.md sections 4.3, 13, 14.

## 1. Placement
| profile | what runs | host | notes |
|---|---|---|---|
| B (hosted demo) | process `edge` = `hosts/edge.py` mounting api-gateway only | Render free web service #1 (V: 750 instance-h/workspace, one instance, ephemeral disk, no shell, no one-off jobs; spins down after 15 min idle, wake ~1 min) | upstreams `core`, `ai` over public HTTPS (free services have no private network, V). `UPSTREAM_MODE=http`. Web on Vercel Hobby proxies `/api/*` to `edge` (Vercel proxied timeout 120 s, V) |
| B single-process fallback | `hosts/all.py` mounts every app incl. gateway | one Render service | triggered by G6 / sprint-plan (cold-start flake > 1 in 10 runs, I). `UPSTREAM_MODE=inprocess`. Loses process isolation; state honestly. Config only, no code change (REQ-GW-031) |
| A (all separate) | gateway in its own container, each service its own container | local `docker compose` (primary), hosted optional | `UPSTREAM_MODE=http`, URLs point at compose service names. Shown to judges as same code, co-location only for free tier |
- Database: Neon Free, pooled (`-pooler`) endpoint, schema `gateway`, role `gateway_app` with grants on that schema only (ADR-004). Do NOT use Render free Postgres (V: expires after 30 days).
- Only `edge` is publicly routable for APIs (via the Vercel rewrite). No other process is a public API surface by design; they still have public URLs on free tiers (V: no private networking), so every service verifies the internal JWT (T14).

## 2. Cold start, sleep, keep-warm (the gateway is the first click)
- Render sleep: 15 min idle, ~1 min wake (V). First judge click after idle can hang; mitigations: pinger, `UPSTREAM_WAKING` 503 + UI "waking server" state, warm-up script.
- Neon: scale to zero after 5 min idle (V), resume latency unknown, commonly ~1-2 s (VC). Session lookup on first call pays it. Accept.
- Python/FastAPI cold boot on a small instance: duration unknown (I). Measure in week 1 on the real host and record here (prd metric). Placeholder: unknown.
- Keep-warm rules (from deployment-zero-cost + spec C12/C13):
  - Pinger target = `GET /healthz` only (no DB). Never ping `/readyz?deep=true` on a schedule (V math: 24/7 DB pings exhaust Neon 100 CU-h free budget in ~16 days).
  - Pingers: UptimeRobot free 5-min (V) as primary, cron-job.org as second (V), GitHub Actions `keepwarm.yml` as third. Pinger set must hit `edge` only.
  - Render 750 h per workspace (V): an always-on `edge` is ~730 h/month, leaving almost no headroom, and any second always-on service suspends all free services at month end. Decision (sprint G6, I): ping `edge` 24/7 only if hours math holds; otherwise ping in review windows and run `scripts/warmup` before recordings. Other processes sleep and are woken by gateway traffic or `scripts/warmup`.
  - Downstream wake chain: gateway -> sleeping `core`/`ai` can add ~1 min each (I from V sleep time). `scripts/warmup` hits `/healthz` on edge, core, ai, paypal, web in parallel, then `/readyz?deep=true` (operator or tick secret), then one dry run.
- Gateway timeouts: `PS_APIGATEWAY_UPSTREAM_CONNECT_TIMEOUT_S` long enough to cover a wake but total budget `PS_APIGATEWAY_UPSTREAM_TOTAL_BUDGET_S` under 120 s (Vercel proxy cap, V). Values chosen after week-1 measurement (no number invented here).
- Cookie topology (R3): Vercel rewrite makes `/api/*` same-site so SameSite=Lax works; test with a real PayPal return in week 1 (task GW-S1-08). If it fails, risk R3 stays open and web needs another mechanism.

## 3. Runtime
- Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic, httpx, PyJWT + cryptography, argon2-cffi (ADR-002; library choice for argon2 is I). `uv` lockfile, `pip-audit` in CI.
- Server: `uvicorn` single worker (in-memory rate limiter and CSRF ledger assume one process; spec 6.3). Start command shape: `uvicorn hosts.edge:app --host 0.0.0.0 --port $PORT`. Behind Render proxy: `TRUSTED_PROXY_COUNT` set to the real hop count (value confirmed in week 1: I).
- Small DB pool (Neon free connection budget unknown: I).
- Logs to stdout as JSON (Render logs; Vercel logs only 1 h, V, so do not rely on them). Optional Sentry (`PS_APIGATEWAY_SENTRY_DSN`).
- No local file state (ephemeral disk, V). No background worker (not free on Render, V): tick comes from cron via `POST /api/ops/tick`.

## 4. Dockerfile outline (services/api-gateway/Dockerfile; actual file written in sprint)
```
FROM python:3.12-slim AS build   # pin by digest in CI (I)
  - install uv; copy pyproject + uv.lock; uv sync --frozen --no-dev (workspace: libs/common, libs/clients, services/api-gateway)
FROM python:3.12-slim
  - create non-root user; copy venv + app + migrations + hosts/edge.py
  - ENV PYTHONUNBUFFERED=1; no secrets in ENV/ARG/layers
  - EXPOSE via $PORT; HEALTHCHECK uses GET /healthz
  - CMD uvicorn hosts.edge:app --host 0.0.0.0 --port ${PORT} (Profile A: services/api-gateway/app.main:app)
```
- Image contains no `.env`, no keys. CI test greps image layers and compose files for secrets (T13). `.dockerignore` excludes `.env*`, tests, docs.

## 5. Environment variables (NAMES ONLY; values live in platform env)
Prefix per agent-context-map section 7 proposal (`PS_<SLUG>_*`, slug api-gateway -> `APIGATEWAY`; the prefix scheme is still I until confirmed). Suffix = the name used in spec.md section 13.
| variable | secret? | notes |
|---|---|---|
| `PS_APIGATEWAY_APP_ENV`, `_DEMO_MODE`, `_LOG_LEVEL` | no | `PS_APIGATEWAY_DEMO_MODE=false` anywhere except demo/staging |
| `PORT` | no | platform-injected, unprefixed |
| `PS_APIGATEWAY_DATABASE_URL` | yes | Neon pooled URL, `gateway_app` role |
| `PS_APIGATEWAY_MIGRATION_DATABASE_URL` | yes | DDL-capable role; CI only (GitHub Actions secret), NOT set on Render (I) |
| `PS_APIGATEWAY_FRONTEND_ORIGINS` | no | exact origins |
| `PS_APIGATEWAY_COOKIE_NAME` | no | default `__Host-ps_sid` |
| `PS_APIGATEWAY_SESSION_TTL_BUYER_S`, `_SESSION_CAP_BUYER_S`, `_SESSION_TTL_STAFF_S`, `_MAX_EPHEMERAL_BUYERS` | no | |
| `PS_APIGATEWAY_CSRF_KEY` | yes | purpose key, never reused (agent-context-map section 4) |
| `PS_APIGATEWAY_SESSION_COOKIE_KEY` | yes | reserved; unused if cookie is purely opaque |
| `PS_APIGATEWAY_SIGNING_KEY_PEM`, `_SIGNING_KID` | yes | Ed25519 current key |
| `PS_APIGATEWAY_PREVIOUS_PUBLIC_KEYS` | no | JSON, JWKS overlap |
| `PS_APIGATEWAY_INTERNAL_TOKEN_TTL_S` | no | default 60, max 120 |
| `PS_APIGATEWAY_UPSTREAM_MODE` | no | `http` or `inprocess` |
| `PS_APIGATEWAY_UPSTREAM_{MANDATE,CATALOG,SHOPPING_AGENT,CHECKOUT,TRACKING,RESOLUTION,AUDIT}_URL` | no | Profile A/B base URLs (Profile B: core/ai public URLs) |
| `PS_APIGATEWAY_UPSTREAM_CONNECT_TIMEOUT_S`, `_READ_TIMEOUT_S`, `_TOTAL_BUDGET_S`, `_RETRIES` | no | set after week-1 measurement |
| `PS_APIGATEWAY_MAX_BODY_BYTES`, `_RATE_LIMIT_*`, `_LLM_DAILY_BUDGET_CALLS` | no | LLM counter is not an LLM key |
| `PS_APIGATEWAY_MONEY_ROUTES_ENABLED` | no | gateway brake; env change needs restart on free hosts (I) |
| `PS_APIGATEWAY_TICK_SECRET` | yes | `X-Tick-Secret` for cron |
| `PS_APIGATEWAY_TRUSTED_PROXY_COUNT`, `_APPROVAL_URL_HOST_ALLOWLIST` | no | allowlist host confirmed in G1 spike (C16) |
| `PS_APIGATEWAY_SENTRY_DSN` | yes | optional |
| `SEED_MERCHANT_PASSWORD`, `SEED_OPERATOR_PASSWORD`, `SEED_BUYER_PASSWORD` | yes | read ONLY by `scripts/seed`, run from a trusted shell/CI; not set on the running service |
- FORBIDDEN in gateway env (CI env-manifest test, REQ-GW-051): `PAYPAL_*`, `LLM_*`, `MANDATE_HMAC_KEY`, `APPROVAL_KEY`. Test also fails if the unprefixed spec names collide with the prefixed scheme in a deploy file.
- `.env.example` lists names only. Agents never read or print `.env`.

## 6. Secrets handling
- Stores: Render env vars (gateway runtime), GitHub Actions encrypted secrets (migration URL, deploy hook, tick secret for cron), Vercel env (only `NEXT_PUBLIC_*` public values). Exact feature limits of each store: I (standard).
- Rules: gitleaks pre-commit + full-history CI; separate keys per purpose; dev values rotated before submission; signing-key rotation drill once before submission (spec 7, auth-gateway 3.4); no tokens, cookies, `token`/`PayerID`/`state` query params in logs (REQ-GW-016).
- Tick secret appears in headers of cron calls only; cron-job.org and UptimeRobot get `/healthz` only (no secret).
- Seed passwords: set in the shell/CI step that runs `scripts/seed`, never committed, hashes made by the script.

## 7. Health and readiness
| endpoint | checks | used by |
|---|---|---|
| `GET /healthz` | process up, no DB | Render health check, UptimeRobot, cron-job.org, deploy health gate, Docker HEALTHCHECK |
| `GET /readyz` | DB reachable + signing key loaded | deploy gate after wake, smoke |
| `GET /readyz?deep=true` | above + upstream `/healthz` fan-out | `scripts/warmup`, nightly warm-up; restricted (operator or tick secret) |
- Render health check path: `/healthz` (shallow, so a cold Neon never fails the deploy; I).

## 8. CI/CD and deploy ritual
- Path-filtered workflow on `services/api-gateway/**`, `libs/**`, `contracts/**`, `hosts/edge.py`: ruff, mypy/pyright (I), pytest, OpenAPI drift check, env-manifest test, gitleaks, pip-audit.
- On main: run migrations (section 9) -> trigger Render deploy (auto-deploy from GitHub or Deploy Hook secret; hook behavior I) -> health gate: `curl --retry` on `/healthz` (covers ~1 min wake, V) then `/readyz` -> smoke (login -> mandate -> cart -> order create via gateway) -> `scripts/warmup` -> log result in sprint log.
- Concurrency group per service; Vercel redeploy only if web changed.

## 9. Migrations (Alembic, services/api-gateway/migrations)
- Tables: `users`, `sessions`, `csrf_uses`, `signing_keys`, `settings` (spec 3).
- Run from CI against Neon with the DDL role BEFORE the new image goes live (Render free has no shell or one-off jobs, V). Fallback if CI cannot reach Neon: run at app start under a Postgres advisory lock (I; adds boot time).
- Expand-and-contract: add nullable/new first, deploy code that tolerates both, backfill, then contract in a later release. Never drop a column in the same release that stops using it. Sessions are disposable: destructive session-table changes are acceptable (users re-login) but `users` seed rows must survive.
- `gateway_app` gets grants on schema `gateway` only; cross-schema SELECT denied (tested, T-ADR-004 item). Seeding via `scripts/seed` is idempotent.
- Migration + signing key: `signing_keys` public keys inserted on rotation, never private keys.

## 10. Rollback
- Code: `workflow_dispatch` redeploy of a previous commit SHA (Render keeps no free rollback guarantee: I; so redeploy by SHA). Health gate re-runs.
- Schema: expand-only migrations mean the previous image still runs; contract steps are never auto-run.
- Keys: keep previous public key in JWKS during overlap; to roll back a signer switch, redeploy previous `PS_APIGATEWAY_SIGNING_KID`/PEM from platform env (previous key must still be accepted by verifiers).
- Emergency brakes (no redeploy beyond restart): `PS_APIGATEWAY_MONEY_ROUTES_ENABLED=false` (gateway brake); `POST /api/ops/freeze` (owner-enforced refund freeze); bump `settings.global_epoch` or user `epoch` to invalidate all sessions (SQL by operator, documented in runbook); `PS_APIGATEWAY_DEMO_MODE=false` to remove demo-control routes.
- If the host itself fails: switch to `hosts/all.py` single process or Profile A compose + recorded video fallback (sprint-plan Backup B/C).

## 11. Free-tier risks specific to the gateway
| risk | label | handling |
|---|---|---|
| Render 750 h/workspace shared | V | only `edge` pinged; re-verify Nov 1 |
| Render suspends on unusually high outbound traffic | V | no tight polling loops from gateway; tick is cron-paced |
| Neon CU-h exhausted by DB pings | V math | pinger on `/healthz` only |
| In-memory limiter resets on sleep | I | provider-side caps, global LLM counter |
| Vercel Hobby non-commercial terms | I (not re-read) | hackathon use; confirm Nov 1 |
| Cookie topology across Vercel/Render | I | rewrite; week-1 test |
