# tracking: deployment (zero cost)

Labels V/VC/I. Free-tier facts come from deployment-zero-cost.md (V there, not re-verified today). Env names only; no values.

## Placement
- Profile B (demo, hosted): tracking runs inside the `core` process (hosts/core.py with mandate, catalog, checkout, resolution, audit). Reason: one warm process for the sync critical path and the in-process poller; a separate tracking process would add a cold hop and, on Render, compete for the 750 h/workspace budget (V).
- Profile A (docker compose, CI, optional rehearsal): tracking is its own container with its own Dockerfile; clients switch from in-process to HTTP via `PS_TRACKING_SERVICE_TRANSPORT`/`*_URL` config only.
- Database: schema `tracking` in the shared Postgres with its own role (ADR-004). Do not use Render free Postgres for the final demo (expires at 30 days, V); host choice belongs to the deployment owner (Neon/Supabase candidates; Supabase pauses after 1 week inactivity, V).

## How polling works when the service sleeps
1. While awake: in-process asyncio interval in core (`PS_TRACKING_TICK_INTERVAL_SECONDS`).
2. While asleep: nothing runs (Render spins down after 15 min idle, wakes ~1 min, V). On wake, lifespan startup runs a catch-up tick; any request to tracking runs lazy per-shipment catch-up.
3. Keep-warm: UptimeRobot 5-min monitor (V) on core `/healthz/deep` (also triggers a rate-limited tick) + cron-job.org backup + GitHub Actions `keepwarm.yml`. Enable pingers only in review/recording windows: 24/7 on one service is ~730 of 750 h (V math), and Neon compute hours would also drain (V math in deployment-zero-cost section 4).
4. Backup: GitHub Actions schedule calls `POST /internal/tick` with `X-Tick-Secret` (secret stored in Actions + Render env).
5. Result: since detection derives from stored facts and sim_now, sleeping delays notice, never correctness. Demo path uses the clock-advance call, which ticks synchronously.

## Env (names only; see spec section 9)
`PS_TRACKING_DB_URL`, `PS_TRACKING_SANDBOX_MODE`, `PS_TRACKING_DEMO_CONTROLS_ENABLED`, `INTERNAL_TICK_SECRET`, `PS_TRACKING_INTERNAL_JWKS_URL`, `PS_TRACKING_INTERNAL_AUDIENCE`, `PS_TRACKING_EVENT_PUSH_HMAC_KEY`, `PS_TRACKING_PAYPAL_ADAPTER_URL`, `PS_TRACKING_CHECKOUT_URL`, `PS_TRACKING_AUDIT_URL`, `PS_TRACKING_RESOLUTION_URL`, `PS_TRACKING_TICK_INTERVAL_SECONDS`, `PS_TRACKING_TICK_LEASE_SECONDS`, `PS_TRACKING_TICK_ENABLE_INPROCESS`, `PS_TRACKING_LATE_GRACE_SECONDS`, `PS_TRACKING_LOST_AFTER_SECONDS`, `PS_TRACKING_LOST_AFTER_PROMISE_SECONDS`, `PS_TRACKING_DEMO_MAX_ADVANCE_SECONDS`, `PS_TRACKING_DEMO_MAX_ACTIONS_PER_MINUTE`, `PS_TRACKING_SERVICE_TRANSPORT`, `PS_TRACKING_LOG_LEVEL`. `tracking` holds NO PayPal credentials and NO LLM keys (those stay in paypal / ai processes). Secrets only in platform env + GitHub Actions secrets; `.env.example` lists empty names; gitleaks in CI.
Hosted-demo posture: `PS_TRACKING_SANDBOX_MODE=true` and `PS_TRACKING_DEMO_CONTROLS_ENABLED=true` are required for the judged demo; if the public instance is left unattended, the operator may set `PS_TRACKING_DEMO_CONTROLS_ENABLED=false` (carrier simulation still runs by script; only manual jumps stop).

## Health
`/healthz` (liveness), `/readyz` (DB, clock row, migrations at head), `/healthz/deep` (keep-warm; ticks). Render health check path: `/healthz`. `scripts/warmup` hits `/healthz/deep` before recordings and prints tick result.

## CI/CD
Path-filtered workflow `services/tracking/**`: ruff, pytest (unit + DB integration against Postgres service container), openapi drift check, gitleaks, pip-audit. Deploy on main via Render deploy hook/auto-deploy; migrations (Alembic) run at start of release (expand-and-contract; additive only during the demo window).

## Rollback
- Code: redeploy previous image/commit (Render rollback or revert + deploy hook).
- Migrations: expand-contract so previous version runs on new schema; no destructive migration in weeks 3-4.
- Operational: `PS_TRACKING_TICK_ENABLE_INPROCESS=false` stops auto ticking (manual `/detector/run` remains); `PS_TRACKING_DEMO_CONTROLS_ENABLED=false` freezes controls; detections are insert-once so a rollback cannot re-fire them. If a bad detection was emitted, fix forward via `demo/clock/reset` (sandbox) or a human-review close in resolution; never delete rows in prod-like env.
- Kill-switch for money lives in resolution/adapter (threat-model section 10); tracking cannot move money, so rolling it back is low-risk.
