# Service skeleton conventions (Wave 4)

Binding for every per-service scaffolding agent. Deviating breaks the contract-first guarantee that lets 11 services build in parallel. If a service's own `spec.md`/`api.md`/`deployment.md` conflicts with this doc on something NOT listed here as "service-specific", this doc wins — flag the conflict in the PR instead of silently picking one.

Source docs per service: `.claude/prd/services/<slug>/{prd,spec,api,deployment,test-plan,sprint-tasks}.md`. Shared facts: `.claude/prd/00-context-brief.md`, `.claude/prd/00-platform-prd.md` §12 (decisions, final), `.claude/prd/architecture/{service-map,data-architecture,auth-gateway,adr}.md`.

## 1. Directory layout (per service, `services/<slug>/`)

```
services/<slug>/
  app/
    __init__.py
    main.py            # FastAPI() app, mounts routers, health/readyz, exception handlers
    settings.py         # pydantic-settings, env prefix PS_<SLUG>_ (SLUG = slug uppercased, hyphens stripped, e.g. paypal-adapter -> PS_PAYPALADAPTER_*, shopping-agent -> PS_SHOPPINGAGENT_*)
    routers/            # one module per resource, matches api.md endpoints exactly
    schemas/            # pydantic request/response models, mirrors contracts/openapi/<slug>.yaml
    deps.py             # FastAPI Depends: db session, auth/JWT verification, idempotency check
    db.py               # async engine/session factory (asyncpg), reads settings.database_url (pooled) / migration_database_url (direct)
  tests/
    unit/
    integration/
    __init__.py
  migrations/
    env.py              # Alembic, version_table_schema=<schema from data-architecture.md §3>
    versions/           # baseline revision only in Wave 4 (creates schema objects + grants via libs/common/db_grants)
    script.py.mako
  Dockerfile
  pyproject.toml         # uv-managed, name = "ps-<slug>"
  alembic.ini
  .env.example           # this service's own vars only, placeholders, matches deployment.md's documented var names exactly (do not invent names not already in deployment.md)
  README.md              # 10-15 lines: what this service does, how to run it alone (`uv run uvicorn app.main:app --reload`), how to test (`uv run pytest`)
```

Every route is a **stub** in Wave 4: implement request validation (pydantic schema from the OpenAPI contract) and return `501 Not Implemented` with body `{"error": "not_implemented", "detail": "<endpoint> pending Wave 5"}` UNLESS the endpoint is `/health`, `/readyz`, or `/healthz` (those must actually work: health returns 200 immediately, readyz checks DB connectivity per `data-architecture.md` §9 pre_ping pattern). Do not implement business logic yet — that is Wave 5 (sprint-plan.md), this wave is contracts + skeleton + migrations + CI-ability only.

## 2. Settings (pydantic-settings)

- Env prefix: exactly `PS_<SLUG>_` where `<SLUG>` = the service slug, uppercased, with `-` removed (matches what's already used in the PRD docs: `paypal-adapter` -> `PS_PAYPALADAPTER_`, `shopping-agent` -> `PS_SHOPPINGAGENT_`, `triage-ai` -> `PS_TRIAGEAI_`, `api-gateway` -> `PS_APIGATEWAY_`).
- The 3 documented exceptions (bare names, no prefix) apply only where that service's `deployment.md`/`spec.md` already names them: `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` (paypal-adapter only), `MANDATE_HMAC_KEY` / `MANDATE_HMAC_KEY_PREVIOUS` (mandate, and any service with a hard-coded test asserting the bare name per `mandate/spec.md` C5), `INTERNAL_TICK_SECRET` (shared cron-trigger name, any service with a `/internal/tick` endpoint).
- Pull the exact variable list straight from that service's `deployment.md` env table — do not invent new ones. If `settings.py` needs a var not yet documented there, add it to both files and note it in the PR/handoff, don't silently add it only in code.
- `DATABASE_URL` is always `PS_<SLUG>_DATABASE_URL` (pooled, runtime) per that service's own convention already in its deployment.md; migrations use `PS_<SLUG>_MIGRATION_DATABASE_URL` (direct) — check the service's actual doc for the literal names (they already exist, grepped and listed below for reference per service; use the real ones, this list is non-exhaustive):
  - mandate: `PS_MANDATE_DATABASE_URL`, `PS_MANDATE_MIGRATION_DATABASE_URL`
  - catalog: `PS_CATALOG_DATABASE_URL`, `PS_CATALOG_SEED_DATABASE_URL`
  - checkout: `PS_CHECKOUT_DATABASE_URL`
  - audit: `PS_AUDIT_DATABASE_URL`, `PS_AUDIT_MIGRATE_DATABASE_URL`
  - resolution: `PS_RESOLUTION_DATABASE_URL`
  - tracking: `PS_TRACKING_DB_URL`
  - triage-ai: `PS_TRIAGEAI_DATABASE_URL`
  - shopping-agent: `PS_SHOPPINGAGENT_DB_URL`
  - paypal-adapter: `PS_PAYPALADAPTER_DATABASE_URL`
  - api-gateway: `PS_APIGATEWAY_DATABASE_URL`, `PS_APIGATEWAY_MIGRATION_DATABASE_URL`

## 3. Health/readiness contract (every service, identical shape)

- `GET /health` -> `200 {"status": "ok", "service": "<slug>"}` — no DB, no downstream calls, must answer even if DB is asleep.
- `GET /readyz` -> `200 {"status": "ready", "db": "ok"}` on a successful `SELECT 1` against the pooled connection (3 retries, backoff, per `data-architecture.md` §9), else `503 {"status": "not_ready", "db": "<error class>"}`.
- These two routes are real in Wave 4, not stubs — CI and `scripts/warmup` depend on them existing now.

## 4. Error envelope (every non-2xx JSON response)

```json
{"error": "<snake_case_code>", "detail": "<human string>", "request_id": "<uuid or null>"}
```
FastAPI exception handler in `main.py` normalizes `HTTPException`, `RequestValidationError`, and uncaught `Exception` (500, generic detail, never a stack trace) into this shape.

## 5. Auth (per `architecture/auth-gateway.md`)

- Services behind the gateway verify an internal service-JWT via `deps.py` (JWKS fetch from the gateway, cached). Stub this as a real `Depends` that actually verifies a JWT (library: `python-jose` or `pyjwt`), reading `PS_<SLUG>_INTERNAL_JWKS_URL` / `PS_<SLUG>_INTERNAL_JWT_AUDIENCE` where that service's deployment.md documents them. In Wave 4, point it at a local static JWKS fixture if the gateway isn't implemented yet (so services can still run standalone); do not fake-pass auth with an `if True`.
- `api-gateway` itself additionally terminates buyer sessions (cookie, see its own spec.md) — only that service's skeleton needs session/cookie code.

## 6. Dockerfile (template, adapt ports/CMD)

```dockerfile
FROM python:3.12-slim AS base
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev || uv sync --no-dev
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## 7. pyproject.toml (template)

```toml
[project]
name = "ps-<slug>"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "pydantic-settings>=2.6",
  "sqlalchemy[asyncio]>=2.0",
  "asyncpg>=0.30",
  "alembic>=1.14",
  "httpx>=0.27",
  "pyjwt>=2.9",
]

[tool.uv]
dev-dependencies = ["pytest>=8", "pytest-asyncio>=0.24", "ruff>=0.7", "mypy>=1.13"]
```
Add service-specific deps only when that service's spec.md requires them (e.g. shopping-agent/triage-ai add an LLM SDK per ADR-010 — Gemini + Groq clients — but keep calls behind `libs/common`'s gateway interface, not scattered `import google.genai` calls in routers).

## 8. OpenAPI contracts (`contracts/openapi/<slug>.yaml`)

Hand-written OpenAPI 3.1 derived from that service's `api.md` (endpoints, request/response schemas, status codes already enumerated there) — do not invent endpoints `api.md` doesn't list, and don't drop any it does. This file is the source of truth for the CI "contract drift" check (Wave 4+: FastAPI's generated schema must match this file once routes are implemented in Wave 5 — for now it just needs to exist and be internally valid YAML/OpenAPI). Money-moving fields use `integer` (minor units) with a `currency` sibling, never `number`/float — matches `data-architecture.md` §5.

## 9. Migrations (Alembic, per `data-architecture.md` §8)

- `migrations/env.py`: `version_table_schema=<schema>` (the service's schema name from `data-architecture.md` §3 table, e.g. mandate -> schema `mandate`), target metadata only for that schema's tables, refuses DDL on any other schema.
- One baseline revision in Wave 4: creates the schema, its tables/columns/constraints exactly as listed in `data-architecture.md` §3 and §6 for that service, plus grants via a call into `libs/common/db_grants` (the shared helper — stub it now with the role names from §4 of that doc: `mig_<slug>` owns, `svc_<slug>` gets the documented SELECT/INSERT/UPDATE grants).
- No data migrations yet except `catalog`'s seed (12 items/3 merchants, from `data-architecture.md` §10) — write that as a second revision now since catalog is read-only at runtime and Wave 5 needs seeded data to demo against immediately.

## 10. What NOT to do in Wave 4

- No real PayPal calls, no real LLM calls, no business logic beyond the two health routes.
- No shared business logic in `libs/` (ADR-009 consequence: libs hold no business logic — only cross-cutting infra: db_grants, JWT verify/mint, the LLM gateway *interface* (not providers), HTTP client wrapper with retry/timeout defaults).
- Don't touch another service's directory. Don't touch `contracts/openapi/` for a service other than your own. Shared files (`docker-compose.yml`, `libs/`, root `pyproject.toml`, `.github/workflows/`) are out of scope for per-service agents — flag if something there needs to change instead of editing it yourself.
