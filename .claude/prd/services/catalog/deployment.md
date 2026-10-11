# catalog - Deployment (zero cost)

Labels: V/VC/I. Facts from deployment-zero-cost.md (Render free: 750 instance-hours per workspace, sleeps after 15 min idle, ~1 min wake: V; Neon Free scales to zero after 5 min idle: V). Not re-verified here; hosts to be re-checked before submission (I).

## Placement
| profile | placement |
|---|---|
| Profile B (demo, submitted) | Module mounted in the `core` process via `hosts/core.py` (with mandate, checkout, tracking, resolution, audit). In-process ASGI calls from checkout; no separate sleep domain. Keeps own router, own DB role, own JWT audience check. |
| Profile A (target topology) | Its own container (Dockerfile in `services/catalog/`). Runs via `docker compose` always; optional hosted rehearsal as separate Render free web service. Sleeps when idle, so callers use timeouts and backoff on resolve (idempotent). |
- Never co-located inside `ai` or `paypal` processes (no LLM keys or PayPal secret in the catalog process).
- Pinned to no PayPal/LLM egress: catalog needs only Postgres and the gateway JWKS URL.

## Runtime
- Python 3.12, FastAPI, uvicorn, SQLAlchemy 2, Alembic, Pydantic v2 (ADR-002). uv workspace, lockfile committed.
- Stateless; no local disk state (Render ephemeral disk: V). Small pool, one worker.
- Image contains the seed JSON; no secrets baked in.

## Environment (names only)
`PS_CATALOG_SERVICE_NAME, PORT, PS_CATALOG_DATABASE_URL, PS_CATALOG_SEED_DATABASE_URL, PS_CATALOG_SEED_ON_START, PS_CATALOG_ADMIN_ENABLED, PS_CATALOG_SEED_FILE, PS_CATALOG_MAX_LINES, PS_CATALOG_MAX_LINE_QTY, PS_CATALOG_INTERNAL_JWKS_URL, PS_CATALOG_INTERNAL_JWT_AUDIENCE, PS_CATALOG_INTERNAL_CALLER_ALLOWLIST, PS_CATALOG_LOG_LEVEL, PS_CATALOG_DB_POOL_SIZE`.
- Secrets live only in platform env (Render/Vercel/GitHub encrypted secrets: I-standard). `.env.example` has names only. gitleaks in pre-commit and CI.
- `PS_CATALOG_SEED_DATABASE_URL` is set only where seeding/admin is enabled; in a locked-down final deployment it can be removed after first seed (I).
- `PS_CATALOG_ADMIN_ENABLED=false` by default; enabled for demo reset only.

## Database
- One Postgres (Neon Free preferred: V per deployment doc), schema `catalog`, roles `catalog_ro` (runtime) and `catalog_seed` (seed/admin/migrations). Do not use Render free Postgres for final demo (expires after 30 days: V).
- Verify on chosen host that role grants and the read-only constraint work (design verified only in principle: I).

## Health and warm-up
- `/healthz` liveness, `/readyz` DB + seed + version (also `/health` alias). Warm-up script (`scripts/warmup`) hits `/readyz` before recording; with Profile B it rides on `core`'s keep-alive.
- Do not add a dedicated 24/7 pinger for catalog (750 h cap is per workspace: V).

## Migrations and seeding on cold start
1. Alembic migration `0001_catalog_schema` creates tables, views, roles' grants; `0002_seed_v1` loads version 1 (service-map: seeded by migration).
2. At startup (`PS_CATALOG_SEED_ON_START=true`) idempotent seed check under an advisory lock; no-op when hash matches. Safe with concurrent starts and with Neon wake delays (retry DB connect with backoff, then `/readyz` 503 until ready).
3. Migrations are additive and backward compatible (expand then contract) so the previous image runs on the new schema.
4. Migrations run in the CI deploy step or at container start via the seed role, never with the runtime role.

## CI/CD
- Path-filtered workflow `services/catalog/**`: ruff, pytest, OpenAPI diff, gitleaks, pip-audit; then deploy via host auto-deploy or deploy hook (I-standard); `curl --retry` on `/readyz` as a health gate (accounts for ~1 min wake).
- Profile B: same workflow builds the `core` image; catalog tests also run in the core process.

## Rollback
- Code: redeploy the previous commit SHA (manual `workflow_dispatch` with SHA). Because migrations are additive and price rows append-only, old code still works.
- Data: `catalog_versions` is append-only, so rolling back "data" means resolve with a pinned `catalog_version` or `POST /admin/reset` re-applying the committed seed as a new version. Never DELETE price rows.
- Alembic downgrade is allowed only in dev/CI; in the hosted DB prefer forward-fix (I).
- Emergency: if catalog is unhealthy, checkout fails closed (cannot re-price). Fall back to restarting `core`; there is no manual price override path by design.

## Honest notes
- Seeded catalog; SIMULATED merchants; sandbox only. Co-location in `core` is for the free tier; catalog is not independently scaled in Profile B and should be described that way.
- Free-tier limits change; re-check before submission (I).
