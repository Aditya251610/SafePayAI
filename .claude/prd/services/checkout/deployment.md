# checkout: deployment (zero cost)

Labels V/VC/I. Free-tier facts below come from `architecture/deployment-zero-cost.md` (read 2026-10-10; official pages cited there). Re-verify before 2026-11-01. No secret values; names only.

## 1. Placement
| Profile | Where | Notes |
|---|---|---|
| B (demo, public link) | `core` process on Render free web service, mounted with mandate, catalog, tracking, resolution, audit (adr ADR-005; Render free: 750 instance-h/mo per workspace, spins down after 15 min idle, ~1 min wake: V) | Checkout -> mandate/catalog/tracking calls are in-process (`PS_CHECKOUT_INPROCESS_TRANSPORT=true`); cold hops reduced to the 4 processes. Calls to `ai` (intent-fit) and `paypal` stay HTTP |
| A (target topology) | own container/service via `docker compose up` locally and CI contract tests; optional one-time hosted rehearsal | Same code; base URLs instead of in-process transport |
- DB: one Postgres (Neon free preferred, pooled endpoint: V per deployment doc), schema `checkout`, role `checkout_app` with grants only on that schema (ADR-004). Do NOT use Render free Postgres (expires 30 days, V).
- Poller/reconcile: in-process asyncio task in `core` plus an external scheduled call to `POST /internal/reconcile` and `/internal/outbox/flush` (GitHub Actions schedule or free pinger with `INTERNAL_TICK_SECRET`); Render cron/worker are not free (V).
- Frontend: `web` on Vercel (Hobby), static/SSR only; no Python on Vercel.

## 2. Return URL, HTTPS, domain (the riskiest hosted piece; UNTESTED, I)
- `return_url` must be a public HTTPS URL. Both `*.onrender.com` and `*.vercel.app` give HTTPS automatically (I standard, not re-read). No paid custom domain (cost).
- Preferred layout: return page is a route of the Vercel app (`/checkout/return`, static shell). It reads `state`, `token`, `PayerID`, then calls the gateway `POST /orders/paypal/return` with retry. A static page survives a sleeping API; the call retries while the API wakes (~1 min, V).
- Cookies: if web (Vercel) and gateway (Render) are different registrable domains, SameSite=Lax cookie is not sent on the cross-site fetch (auth-gateway s2.3, I). Preferred fix: Vercel rewrites `/api/*` to the gateway so the browser sees one site. Fallback: `SIGN_IN_REQUIRED` screen (state stays unconsumed) then user continues; checkout never auto-captures without a principal.
- `PS_CHECKOUT_RETURN_BASE_URL` comes from env, never hardcoded: preview deployments get different URLs (V per deployment doc s5). Local dev: `cloudflared tunnel --url` gives a random URL per run (V); update the env var each run.
- Whether PayPal sandbox requires pre-registering return URLs for Orders v2: not known (I); test in week 1.
- Referrer: gateway sets `Referrer-Policy: no-referrer`; logs strip query (PayPal `token` and our `state` are in the URL).
- Before the buyer clicks "Approve at PayPal", web fires a warm-up GET to `/readyz` through the gateway so the API is awake when PayPal redirects back.
- Webhooks: not used (hint-only, untested); Render receiver could time out while asleep.

## 3. Env var names (checkout service; values only in platform env)
`PS_CHECKOUT_DATABASE_URL`, `PS_CHECKOUT_DB_POOL_SIZE`, `PS_CHECKOUT_INTERNAL_JWKS_URL`, `PS_CHECKOUT_INTERNAL_JWT_AUDIENCE`, `PS_CHECKOUT_SERVICE_SIGNING_KEY`, `PS_CHECKOUT_SERVICE_SIGNING_KID`, `PS_CHECKOUT_CATALOG_BASE_URL`, `PS_CHECKOUT_MANDATE_BASE_URL`, `PS_CHECKOUT_SHOPPING_AGENT_BASE_URL`, `PS_CHECKOUT_PAYPAL_ADAPTER_BASE_URL`, `PS_CHECKOUT_AUDIT_BASE_URL`, `PS_CHECKOUT_TICKET_HMAC_KEY`, `PS_CHECKOUT_RETURN_BASE_URL`, `PS_CHECKOUT_RETURN_STATE_TTL_SECONDS`, `PS_CHECKOUT_ORDER_APPROVAL_TTL_SECONDS`, `PS_CHECKOUT_CURRENCY`, `PS_CHECKOUT_HTTP_TIMEOUT_*_MS`, `PS_CHECKOUT_RECONCILE_GRACE_SECONDS`, `PS_CHECKOUT_PENDING_POLL_MAX_ATTEMPTS`, `PS_CHECKOUT_OUTBOX_FLUSH_INTERVAL_SECONDS`, `INTERNAL_TICK_SECRET` (deliberately unprefixed, shared cron-trigger name across services), `PS_CHECKOUT_INPROCESS_TRANSPORT`, `PS_CHECKOUT_LOG_LEVEL`, `PS_APIGATEWAY_CORS_ALLOWED_ORIGINS` (owned by api-gateway, listed here for context only).
- In repo: `.env.example` and `services/checkout/env.manifest` list names only. CI test asserts forbidden names are absent: `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `LLM_API_KEY`, `MANDATE_HMAC_KEY`, `APPROVAL_KEY`.
- `PS_CHECKOUT_TICKET_HMAC_KEY` is shared only with paypal-adapter (verifier, which references it as `PS_CHECKOUT_TICKET_HMAC_KEY` too — named after the minting service, not the holder); distinct from every other key (purpose-separated keys, auth-gateway s8).
- gitleaks pre-commit and CI; no secrets in docs, logs, or the frontend bundle.

## 4. Health and warm-up
- `GET /healthz` liveness (no DB). `GET /readyz` DB ping + dependency flags (degraded, not fatal).
- DB-touching pings burn Neon compute hours (5 min idle suspend; 24/7 pings exhaust the monthly budget in about 16 days per deployment doc math, V): ping only during review/recording windows (deployment doc s4).
- Run `scripts/warmup` before recording and before judges: hit all process `/healthz` in parallel, `/readyz`, then a dry-run through create-mandate -> cart -> order create only (stop before approval).
- Only one always-on Render service fits the 750 h cap (V): pinger on the `edge` entry; do not ping `core` 24/7 outside windows. Chain gateway -> core wake cost is accepted and warmed.

## 5. CI/CD
- GitHub Actions path-filtered on `services/checkout/**`, `libs/**`, `contracts/**`: ruff, pytest (unit, contract, compose integration), pip-audit, gitleaks, OpenAPI diff vs `contracts/openapi/checkout.json`.
- Deploy: Render deploy hook / auto-deploy for `core`; migration step `alembic upgrade head` for schema `checkout` before traffic (expand-and-contract; additive only during demo window).
- Health gate after deploy: `curl --retry` on `/healthz` through the gateway (allows ~1 min wake).
- Concurrency group per process to avoid parallel deploys.

## 6. Rollback
- Code: redeploy previous commit SHA (manual `workflow_dispatch` with SHA). Keep the last known-good SHA noted in README before recording.
- Schema: expand-and-contract; no destructive migration in the last week; downgrade migration tested in CI for the latest revision.
- Data: in-flight orders are resumable from `orders.status`; after rollback run `POST /internal/reconcile`.
- Kill/pause: set `MONEY_ENABLED=false` at paypal-adapter (checkout then returns `MONEY_DISABLED`, no loops). Demo fallback: pre-recorded video segment of the approve/capture click if the sandbox is down (labelled as recorded).
- Free-tier risks owned here: cold start on redirect (R3), Neon suspend/resume, Render hour cap, LLM 429 on intent-fit (degrades to NEEDS_BUYER_CONFIRMATION).
