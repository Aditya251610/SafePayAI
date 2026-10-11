# Tech Stack (consolidated reference — SafePayAI)

Labels: **V** = found explicitly in a cited doc. **I** = inference bridging a gap (never an invented tool — only a connective assumption). No new choices are made here; this consolidates decisions already made elsewhere. Date 2026-10-10.

This doc only restates and cross-links. For rationale/trade-offs, read the cited source.

## 1. Languages & runtimes

| Item | Value | Label | Source |
|---|---|---|---|
| Backend language | Python 3.12 | V | adr.md ADR-002; services/api-gateway/deployment.md ("Python 3.12, FastAPI... ADR-002") |
| Backend package/dep manager | `uv` (workspace + lockfile) | V | adr.md ADR-002, ADR-009; ci-cd-and-repo-workflow.md §5,7 |
| Frontend language/runtime | TypeScript, Next.js (Node runtime implied by Next.js) | V | adr.md ADR-002 ("Frontend: Next.js (TypeScript) as `web`"); services/web/prd.md §1, REQ-WB-001 |
| Frontend package manager | pnpm | V | adr.md ADR-009 ("monorepo (uv workspace + pnpm for web)"); ci-cd-and-repo-workflow.md §5,7 |
| Node version pin | not specified anywhere | — | **Unresolved** (see end) |

## 2. Backend framework & key libraries (ai / core / edge / paypal processes)

Common stack across all 10 backend services (api-gateway, mandate, catalog, shopping-agent, checkout, paypal-adapter, tracking, resolution, triage-ai, audit):

| Library/tool | Role | Label | Source |
|---|---|---|---|
| FastAPI | web framework, per-service app | V | adr.md ADR-002; service-map.md §1 (every service "is a self-contained FastAPI app") |
| Pydantic v2 | schema validation (request/response + LLM output, `extra="forbid"`) | V | adr.md ADR-002; agent-and-mcp-design.md §1 |
| SQLAlchemy 2 + Alembic | ORM + migrations, per-service schema, `version_table_schema=<schema>` | V | adr.md ADR-002; data-architecture.md §8 |
| httpx | inter-service HTTP calls | V | adr.md ADR-002; services/api-gateway/deployment.md |
| PyJWT + `cryptography` | internal service-token signing/verification (EdDSA/Ed25519 or ES256; HS256 fallback) | V | services/api-gateway/deployment.md §(config); auth-gateway.md §3.1,3.3; adr.md ADR-006 |
| argon2-cffi | buyer/merchant password hashing | V (library choice itself flagged I in source) | adr.md ADR-006; services/api-gateway/deployment.md ("argon2-cffi (ADR-002; library choice for argon2 is I)") |
| uvicorn | ASGI server, single worker per process (in-memory rate limiter/CSRF ledger assume one process) | V | services/api-gateway/deployment.md |
| LLM SDK / client | no fixed vendor SDK — a custom `LLMClient.complete_json(...)` abstraction in `llm-gateway` package, provider chosen by env var (Gemini API, Groq, OpenRouter) | V | agent-and-mcp-design.md §1; llm-cost-and-latency.md §1; services/shopping-agent/deployment.md, services/triage-ai/deployment.md |
| FastMCP (Python MCP SDK) | mounts paypal-adapter's own MCP server at `/mcp` | V (SDK API itself flagged "verify current" I) | agent-and-mcp-design.md §3 |
| pytest | unit/integration test runner | V | test-strategy.md §2 (L1-L3); ci-cd-and-repo-workflow.md §5 |
| Schemathesis | contract/property-based fuzz against OpenAPI specs | V | test-strategy.md §2 L2; ci-cd-and-repo-workflow.md §5 |
| Hypothesis | property tests (canonical hash stability, state-machine invariants) | V | test-strategy.md §2 L1 |
| ruff | lint + format | V | ci-cd-and-repo-workflow.md §5 |
| mypy (or pyright) | strict type check on `app/` | V | ci-cd-and-repo-workflow.md §5 |
| pip-audit | dependency vulnerability audit | V | ci-cd-and-repo-workflow.md §7; services/paypal-adapter/deployment.md |
| testcontainers / CI service container (Postgres) | ephemeral-schema integration tests | V | test-strategy.md §2 L3 |
| toxiproxy (or adapter-double fault modes) | chaos/fault injection (L6) | V | test-strategy.md §3 |
| freezegun | fake clock in unit tests | V | test-strategy.md §6 |
| mutmut | mutation testing on `evaluate()`, policy engine, `proposal_hash` | V | test-strategy.md §10 |

## 3. Frontend stack

| Item | Value | Label | Source |
|---|---|---|---|
| Framework | Next.js (TypeScript), one app, two route groups `(buyer)`/`(merchant)` | V | adr.md ADR-002; services/web/prd.md REQ-WB-001 |
| Hosting | Vercel (Hobby tier) | V | deployment-zero-cost.md §3(a); services/web/prd.md REQ-WB-001, §6 |
| UI component layer | shadcn/ui | V (user decision) | user decision 2026-10-10, not an ADR — see §3.1 |
| Animation | Framer Motion | V (user decision) | user decision 2026-10-10, not an ADR — see §3.1 |
| 3D / visual effects | WebGL (via a thin React wrapper, e.g. react-three-fiber or an Aceternity-bundled primitive — exact library left to implementation) | V (user decision) | user decision 2026-10-10, not an ADR — see §3.1 |
| Visual component pack | Aceternity UI | V (user decision) | user decision 2026-10-10, not an ADR — see §3.1 |
| Data grid | AG Grid (Community features only) | V | services/web/prd.md §4, REQ-WB-040/044/045; R8 flags enterprise-feature risk |
| Runtime response validation | zod | V | services/web/prd.md REQ-WB-058 |
| Testing | Playwright (e2e, incl. a11y via axe), vitest, eslint, `tsc --noEmit` | V | test-strategy.md §2 L5; ci-cd-and-repo-workflow.md §5 ("Web (`services/web`)") |
| Python on frontend host | explicitly NOT used (Vercel is static/SSR only; no Python functions) | V | checkout/deployment.md §1; mandate/deployment.md §1 |

### 3.1 Frontend stack decision — Framer Motion + Next.js + shadcn/ui + WebGL + Aceternity UI

- Status: **user decision** (2026-10-10), explicit and confirmed — not an ADR, not architecture-team-originated, and not re-litigated here. Labelled V because the choice itself is a verified fact of record, not a vendor claim.
- Supersedes the plain-Next.js framing implied by ADR-002/ADR-009 (those ADRs fixed the framework/monorepo mechanics — Next.js+TypeScript+pnpm — and are still correct; they said nothing about a component/animation/3D layer, which is what this decision adds).
- Scope: Next.js stays the framework (ADR-002 unchanged). shadcn/ui is the baseline component layer everywhere. Framer Motion and Aceternity UI/WebGL are used selectively — see the risk notes below and services/web/spec.md §10 for the screen-by-screen split.

### 3.2 Frontend technical risk notes (V/I)

| # | risk | label | mitigation |
|---|---|---|---|
| T1 | WebGL compatibility: not all judge/demo browsers or low-power devices render WebGL reliably; context loss, GPU driver variance, and `prefers-reduced-motion` users all need a non-WebGL fallback | I | Confine WebGL to the landing/hook moment only (non-money-path); feature-detect and fall back to a static hero image/CSS gradient on failure or `prefers-reduced-motion` |
| T2 | Bundle-size risk: Aceternity components and WebGL/3D libraries (e.g. three.js) are heavy; Vercel Hobby has a 100 MB upload cap and cold-start/build-time budgets already tight (deployment-zero-cost.md §1) | V (limits)/I (impact) | Code-split so the landing bundle is the only one paying the WebGL/Aceternity cost (dynamic `import()`, route-level chunking); money-path routes never import these packages |
| T3 | SSR-hydration risk: WebGL/canvas-based components typically need `ssr: false` / client-only rendering, which can cause layout shift or hydration mismatches on first paint | I | Render these components client-only with explicit loading/skeleton states; keep them out of any route that also needs the honesty/SANDBOX banner to paint instantly |
| T4 | Aceternity component weight: many Aceternity primitives bundle their own animation/canvas logic beyond what Framer Motion alone needs, compounding T1/T2 | VC (vendor pattern, common to such libraries) | Cherry-pick only the specific Aceternity components used for the hero/landing moment; do not adopt the library wholesale |
| T5 | Animation interference with trust/honesty copy: motion and 3D effects can distract from or visually compete with labels judges must read cleanly (SIMULATED/CACHED/ILLUSTRATIVE, banned-claims text) — see services/web/spec.md's trust/honesty copy rules | V (rule) / I (risk) | **Mitigation (binding):** confine WebGL/Aceternity effects to non-money-path screens — the landing/hook moment and transitions between major sections only. Mandate signing, cart approval/checkout handoff, receipt, refund offer/approve, audit log/verify-chain, and human-review queue screens stay plain shadcn/ui + light Framer Motion (simple opacity/fade transitions) only, with `prefers-reduced-motion` respected throughout (REQ-WB-053, spec.md §6) |

These risks were not asked to be re-litigated — they are recorded here as the technical-risk record the user asked for, alongside the mitigation that confines heavy effects away from the money/trust path.

## 4. Data layer

| Item | Value | Label | Source |
|---|---|---|---|
| Database | PostgreSQL, one managed instance (Neon Free preferred) | V | adr.md ADR-004, ADR-005; data-architecture.md §1-2 |
| Topology | schema-per-service (10 schemas, none for `web`), role-per-schema, no cross-schema SQL/FKs | V | adr.md ADR-004; data-architecture.md §2-4 |
| Pooling | PgBouncer transaction-mode pooled endpoint (`-pooler`) for runtime; direct (non-pooled) connection for migrations/pg_dump | V | data-architecture.md §1,2,9 |
| Migrations tool | Alembic, per-service, `version_table_schema=<schema>`, expand/contract releases | V | adr.md ADR-002/ADR-004; data-architecture.md §8 |
| Driver (asyncpg vs psycopg3) | undecided, explicit open item | — | data-architecture.md §14 item 5 — **Unresolved** |
| Local dev DB | `postgres:16` via docker compose, matching Neon's major version ("check console, I") | I | data-architecture.md §11 |

## 5. Messaging / eventing approach

| Item | Value | Label | Source |
|---|---|---|---|
| Pattern | Postgres transactional outbox + HTTP push to subscriber, with `GET /internal/outbox?after=seq` pull catch-up | V | adr.md ADR-003; overview.md §7 (Option 3, chosen over LISTEN/NOTIFY and a free broker) |
| Delivery semantics | at-least-once, per-aggregate best-effort ordering; consumers dedupe via inbox table / `event_id` unique | V | adr.md ADR-003; data-architecture.md §7 |
| Transport mechanism in Profile B | in-process dispatch when subscriber is co-located, HTTP otherwise (config, not code) | V | overview.md §7,8 |
| Saga | exactly one — the refund saga, owned by `resolution`, orchestration-style | V | adr.md ADR-011; overview.md §6 |
| Event contracts | JSON Schema per event in `contracts/events/<name>.v1.json`, additive-only | V | overview.md §7; adr.md ADR-008 |

## 6. Auth & secrets approach (at a glance)

| Item | Value | Label | Source |
|---|---|---|---|
| Identity provider | Option A — gateway-owned sessions + seeded/ephemeral demo personas (no external IdP) | V | adr.md ADR-006; auth-gateway.md §1 |
| Browser session | opaque 256-bit session id, httpOnly+Secure+SameSite=Lax `__Host-` cookie | V | auth-gateway.md §1 |
| Service-to-service auth | short-lived (≤60s) signed internal JWT, EdDSA/Ed25519 or ES256 pinned per issuer, `aud`-bound, verified via a static `trusted_issuers` map (no runtime JWKS fetch) | V | adr.md ADR-006; auth-gateway.md §3.1 |
| Fallback transport auth | shared-secret HMAC per caller/callee pair | V | auth-gateway.md §3.3 |
| Password hashing | argon2 | V | adr.md ADR-006 |
| Secrets storage | platform env only (Render/Vercel/GitHub Actions secrets dashboards); `.env.example` placeholders only in repo; gitleaks pre-commit + CI | V | deployment-zero-cost.md §6; ci-cd-and-repo-workflow.md §6,9 |
| Credential isolation | only `paypal-adapter` holds PayPal creds; only `shopping-agent`/`triage-ai` hold LLM keys | V | adr.md ADR-010; service-map.md §1; auth-gateway.md §3.2 |

## 7. AI/LLM providers (routing order)

| Task | Primary | Fallback 1 | Fallback 2 (always works) | Label | Source |
|---|---|---|---|---|---|
| Cart proposal | Gemini Flash-class (free, JSON schema) | Groq gpt-oss-120b (JSON mode) | Deterministic/manual cart (buyer picks from catalog) | V | llm-cost-and-latency.md §1 |
| Intent-fit check | Gemini Flash-Lite | Groq gpt-oss-20b | `NEEDS_BUYER_CONFIRMATION` (skip) | V | llm-cost-and-latency.md §1 |
| Triage classification | Groq gpt-oss-20b | Gemini Flash-Lite | Keyword rules → `HUMAN_REVIEW` | V | llm-cost-and-latency.md §1 |
| Message drafting | Gemini Flash | Groq gpt-oss-120b | Static templates (no LLM) | V | llm-cost-and-latency.md §1 |
| Reviewer brief | Gemini Flash | Groq gpt-oss-120b | Template summary from DB | V | llm-cost-and-latency.md §1 |
| Shadow/eval only | OpenRouter `:free`, Cloudflare Workers AI | n/a | n/a (never prod) | V | llm-cost-and-latency.md §1 |

Routing owned by one `llm-gateway` service/package; model IDs are config not code; kill switch `LLM_ENABLED=false` fails everything closed to deterministic/manual/HUMAN_REVIEW paths (V, llm-cost-and-latency.md §2,7). Provider/model final pin is explicitly still open (adr.md ADR-010: "Provider/model choice deferred").

## 8. Hosting / deployment matrix

Profile B (hosted demo, primary) vs Profile A (fully separated, Dockerfile-per-service; local `docker compose` + CI, fallback/architecture-reference topology). Per adr.md ADR-005 and deployment-zero-cost.md §3; per-process detail from service `deployment.md` files.

| Process/service | Profile B host | Profile A host | Profile | Source |
|---|---|---|---|---|
| `edge` (api-gateway, + Vercel proxies web) | Render free web service #1 | own container, `docker compose` | B primary / A fallback | overview.md §8; services/api-gateway/deployment.md |
| `core` (mandate, catalog, checkout, tracking, resolution, audit) | Render free web service #2 | each its own container | B primary / A fallback | overview.md §8; services/checkout, mandate deployment.md |
| `ai` (shopping-agent, triage-ai, `llm-gateway` package) | Render free web service #3 | each its own container | B primary / A fallback | overview.md §8; services/shopping-agent, triage-ai deployment.md |
| `paypal` (paypal-adapter + MCP server) | Render free web service #4, always separate from `ai`/`core`/`edge` (credential boundary) | own container | B primary / A fallback | overview.md §8; services/paypal-adapter/deployment.md |
| `web` | Vercel (Hobby), static/SSR, CDN-warm | Vercel (same) | both | overview.md §8; services/web/prd.md |
| Database | Neon Free (pooled endpoint), one project/instance | same Neon project, `dev`/per-PR branches for CI | both | adr.md ADR-004/005; data-architecture.md §1-2 |
| Single-process fallback | `hosts/all.py` mounting every app (triggered if cold-start flake > 1-in-10) | n/a | B contingency | services/api-gateway/deployment.md |

Supporting infra (V, deployment-zero-cost.md §1,9): GitHub Actions (CI + scheduled keep-warm), UptimeRobot (5-min pinger on `edge` only) + cron-job.org (backup pinger), Sentry Developer (errors, optional), Grafana Cloud Free (logs/metrics, optional). Render's 750 instance-h/workspace cap means only one process (`edge`) can be pinged 24/7; `core`/`ai`/`paypal` sleep and are woken by gateway fan-out + `scripts/warmup`.

## 9. CI/CD tooling

| Tool | Role | Label | Source |
|---|---|---|---|
| GitHub Actions | CI (lint/type/unit/contract/integration/build per service via reusable `ci-python-service.yml`), scheduled keep-warm, deploy trigger | V | ci-cd-and-repo-workflow.md §5,8 |
| gitleaks | secret scanning (pre-commit `protect --staged` + CI `detect` full-history + weekly cron) | V | ci-cd-and-repo-workflow.md §6; deployment-zero-cost.md §6 |
| pre-commit | hook runner (gitleaks, ruff, end-of-file, large-file) | V | ci-cd-and-repo-workflow.md §6 |
| Dependabot | pip/npm/docker/actions dependency bumps, weekly grouped | V | ci-cd-and-repo-workflow.md §7 |
| pip-audit / pnpm audit | dependency vuln scanning in `deps.yml` | V | ci-cd-and-repo-workflow.md §7 |
| GitHub Secret scanning + Push protection | public-repo secret leak prevention | V | ci-cd-and-repo-workflow.md §6 |
| commitlint (or `cz` check) | conventional-commit enforcement on PR title | V | ci-cd-and-repo-workflow.md §2 |
| openapi-diff | breaking-change check vs `main` for committed OpenAPI specs | V | ci-cd-and-repo-workflow.md §5; test-strategy.md §2 L2 |
| CycloneDX (`cyclonedx-py`, `@cyclonedx/cyclonedx-npm`) | SBOM-lite on release tag | V | ci-cd-and-repo-workflow.md §7 |
| Render Deploy Hook / auto-deploy | deploy trigger after CI green, migrations-first ordering | V | ci-cd-and-repo-workflow.md §8; services/paypal-adapter, mandate deployment.md |
| Vercel Git integration | preview-per-PR + production deploy for `web` | V | ci-cd-and-repo-workflow.md §8 |

## 10. Dev tooling (linters, formatters, pre-commit)

| Tool | Scope | Label | Source |
|---|---|---|---|
| ruff (check + format) | Python lint/format | V | ci-cd-and-repo-workflow.md §5 |
| mypy / pyright | Python strict typing | V | ci-cd-and-repo-workflow.md §5 (tool choice itself flagged "I: tool choice") |
| eslint, `tsc --noEmit` | frontend lint/typecheck | V | ci-cd-and-repo-workflow.md §5 |
| `.pre-commit-config.yaml` | gitleaks + ruff + end-of-file + large-file hooks | V | ci-cd-and-repo-workflow.md §6, §12 |
| Editor/IDE config (`.editorconfig`, VS Code settings, etc.) | not named anywhere | — | **not yet specified — TODO** |
| Formatter for TS/web (prettier or built into eslint config) | not explicitly named | — | **not yet specified — TODO** (ci-cd-and-repo-workflow.md only names eslint/tsc for web, no formatter tool) |

## 11. Why this stack

One Python/FastAPI backend and one Next.js frontend were chosen because the team is AI coding agents working a ~33-day hackathon horizon, so a single backend language keeps every agent-sized service unit (ADR-001's 10 services) interchangeable and lets `libs/` stay thin without per-service tooling drift (adr.md ADR-002, ADR-009). The zero-cost constraint drove the Postgres-outbox-over-broker choice (ADR-003), the schema-per-service-on-one-Neon-instance choice (ADR-004), and Profile B's co-location of 10 services into 4 Render processes plus Vercel (ADR-005, deployment-zero-cost.md) — all deliberately reversible (config, not code, switches Profile A/B) because free-tier limits and even the LLM provider are still being re-verified against a moving target. Gateway-owned sessions and a custom MCP server (ADR-006, ADR-007) avoid adding any paid/pausing external vendor, which matters because every added dependency is a new cold-start or quota risk against the 2026-11-10 submit date.

## Unresolved (no existing doc specifies)

- Node.js version pin for the `web` app (framework is Next.js/TypeScript via pnpm, but no Node version is stated anywhere read).
- Pinned dependency versions (exact FastAPI/Pydantic/SQLAlchemy/Next.js version numbers) — docs say "SQLAlchemy 2", "Python 3.12", "Next.js" but no `pyproject.toml`/`package.json` versions are committed in these docs; `uv.lock`/`pnpm-lock.yaml` are the intended source of truth (ci-cd-and-repo-workflow.md §7) but not reproduced here.
- Postgres driver choice behind PgBouncer: asyncpg vs psycopg3 (data-architecture.md §14 explicit open item #5).
- Final LLM provider/model pin (adr.md ADR-010: "deferred, needs free-tier check"; llm-cost-and-latency.md: "Freeze models by 2026-11-05").
- Exact Neon default CU and inactivity-deletion policy (data-architecture.md §1, §14 item 1).
- Frontend code formatter (prettier or equivalent) — not named in any doc read.
- Editor/IDE shared config — not named in any doc read.
- OSS license choice (MIT vs Apache-2.0) — ci-cd-and-repo-workflow.md §10, §12 flags as open.
- Render pre-deploy-command vs CI-driven migration step — explicitly open per mandate/deployment.md §(migrations) ("Fallback if blocked... I").
