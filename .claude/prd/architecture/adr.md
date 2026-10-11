# ADRs (short). Labels: V verified, VC vendor claim, I inference.

## ADR-001 Microservices over modular monolith
- Status: Accepted (user requirement).
- Context: team = AI coding agents, ~33 days, zero-cost hosting that sleeps, money path with sandbox flakiness.
- Decision: 10 backend services + 1 web, with Profile B co-location for the demo.
- Consequences: (+) credential and LLM isolation is structural, clear agent-sized work units, contract-first. (-) more auth/contracts/ops, cold-start risk (I), more integration testing. A modular monolith would be cheaper and safer; we pay this cost knowingly. Mitigation: ADR-003, Profile B.

## ADR-002 Python 3.12 + FastAPI everywhere (backend)
- Status: Accepted. Context: user preference; OpenAPI is free; Pydantic gives schema validation for LLM output.
- Decision: FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic, httpx, uv workspace. Frontend: Next.js (TypeScript) as `web`.
- Consequences: one language for agents to master; shared `libs/` possible. (-) Python async cold start on small free instances (I).

## ADR-003 Events: Postgres transactional outbox + HTTP push (+ pull catch-up)
- Status: Accepted. Context: free tiers, sleeping services, no desire for another vendor.
- Options: LISTEN/NOTIFY (fails with poolers/sleep/cross-DB), free broker (extra vendor/limits), outbox+HTTP (chosen).
- Consequences: (+) zero new infra, works in both profiles, retries wake sleeping consumers. (-) at-least-once only, no replay platform; consumers must dedupe.

## ADR-004 Data: one managed Postgres, schema-per-service, role-per-schema
- Status: Accepted (revisit if host changes). Context: free tiers typically allow 1 (or very few) free DB projects (I).
- Decision: one Postgres instance; each service has its own schema and own DB role with grants only on that schema; audit role INSERT/SELECT only; Alembic per service. No cross-schema SQL or FKs.
- Consequences: (+) cheap, simple, boundary enforced by grants. (-) shared failure domain and shared connection limits (use small pools); not true DB-per-service; a single free DB pausing (I) takes all down, so warm-up applies to DB too. Moving a schema to its own DB later is a connection-string change.

## ADR-005 Hosting: free-tier PaaS per process; Profile B for the demo
- Status: Proposed (needs limits re-verified; all I). Candidate: Render free web services (sponsor prize alignment; sleeps when idle, I), Vercel for `web`, a free Postgres host (Neon or Supabase, I).
- Decision: containers deployable to any host (Dockerfile per service, host file per profile). Demo = Profile B + keep-alive pings + warm-up script.
- Consequences: portable; the "sponsor prize" choice is not locked in code. Only ONE sponsor prize per project, so decide before submission.

## ADR-006 Auth: gateway-owned sessions with seeded demo accounts; internal signed tokens; IdP pluggable
- Status: Accepted. Context: judges need frictionless access; an external IdP is another cold/rate-limited dependency; user wants ONE common auth gateway.
- Decision: api-gateway authenticates (seeded buyer/merchant accounts, argon2 passwords, HttpOnly session cookie), then mints a 60-120 s internal JWT (EdDSA, `aud`=target service, `sub`, `role`, `jti`) verified by every service via cached JWKS. OIDC verifier interface left for a later IdP (Supabase Auth/Auth0 free, I).
- Consequences: (+) fewer vendors, full control, services deny by default. (-) not production-grade identity; never claim so. Single shared merchant login (no per-merchant accountability).

## ADR-007 Own MCP server over PayPal REST, hosted inside paypal-adapter
- Status: Accepted. Context: official `@paypal/mcp` exists (V per PayPal docs) but untested from a backend; our verified surface is REST (brief section 3).
- Decision: expose a minimal MCP tool set (create_order, get_order, capture_order, add_tracking, refund_capture, get_refund) implemented over the same adapter functions as the REST routes; per-tool caller allowlist; LLM services get no MCP access.
- Consequences: (+) deterministic, tested, idempotency ledger enforced, doubles as an agentic-commerce surface. (-) we maintain tool schemas; not "the official MCP", say so plainly.

## ADR-008 Cross-service contracts: OpenAPI 3.1 + JSON Schema events, contract-first CI
- Status: Accepted. Decision: committed specs under `contracts/`, generated clients, CI diff check, consumer-driven smoke tests in compose. Consequences: agents can build services in parallel from specs; (-) spec drift must be policed by CI.

## ADR-009 Monorepo (uv workspace + pnpm for web)
- Status: Accepted. Context: public repo with OSS license required; AI agents benefit from one checkout; shared contracts.
- Layout:
```
safepayai/
  README.md  LICENSE  .env.example  .gitleaks.toml  docker-compose.yml
  contracts/{openapi,events}/
  libs/{common,clients,events}/        # tiny: token verify, outbox, logging, generated clients
  services/<slug>/{app/,tests/,migrations/,Dockerfile,pyproject.toml,README.md}
  services/web/                         # Next.js (slug: web)
  hosts/{edge,core,ai,paypal}.py        # Profile B process mounts
  deploy/{profile-a,profile-b}/         # per-host config (render.yaml etc.)
  scripts/{warmup,seed,demo-reset}/
  docs/ .github/workflows/
```
- Consequences: (-) shared `libs/` can become a hidden coupling point; rule: libs hold no business logic.

## ADR-010 LLM isolation and fail-closed contract
- Status: Accepted. Decision: only shopping-agent and triage-ai hold LLM keys; both validate output against JSON Schema; every failure maps to the restrictive default; triage-ai has no outbound service calls and receives data in-request; raw model output never reaches money services (only validated enums/IDs). Consequences: (-) model downtime degrades UX, never safety. Provider/model choice deferred (needs free-tier check, I).

## ADR-011 Single refund saga owned by resolution; adapter is idempotency backstop
- Status: Accepted. Decision: resolution persists request_id before calling adapter; adapter keeps its own ledger and rejects missing/mutated-amount replays for a used request_id (V: PayPal itself returns the original refund even if the amount differs, so we must enforce this ourselves). 409/timeout -> UNKNOWN -> reconcile via GET. Consequences: (+) no double refund. (-) two ledgers to keep consistent; reconcile job required.
