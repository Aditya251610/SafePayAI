# shopping-agent: deployment

Labels: V verified (read today), VC vendor/secondary, I inference/unverified. Sources: `architecture/deployment-zero-cost.md`, `architecture/llm-cost-and-latency.md`, `architecture/adr.md` (ADR-005, ADR-009). No secret values here; env NAMES only. Re-check free-tier facts before 2026-11-01 (they change).

## 1. Placement

### Profile B (demo; ADR-005, ADR-009)
- shopping-agent code runs mounted inside the `ai` process (`hosts/ai.py`), alongside `triage-ai` and the shared `llm-gateway` package. One Render free web service, one cold-start domain for this process (I, per deployment-zero-cost doc recommendation (a): fewest moving parts).
- `llm-gateway` is a package inside the `ai` process, NOT a separate service (user decision, locked): it owns provider keys, routing, cache, budgets, breaker; there is no network hop between shopping-agent and the gateway in Profile B.
- This service keeps its own router, own DB role (`agent` schema, ADR-004), own audience check (`aud=shopping-agent`) even though it shares a process — identical code path to Profile A (no behavioral difference, only network topology differs).
- Reaches `catalog` and `mandate` (read-only) over the Profile B process boundary (same deploy, different FastAPI app mounts; calls are still real HTTP in-cluster or in-process function calls depending on final `hosts/ai.py` wiring — I, confirm with overview.md host wiring before freeze).
- No PayPal credential and no PayPal network route in this service's env or egress allowlist (ADR-010, threat-model B4).

### Profile A (fully separated services; architecture docs, not the submitted demo topology)
- shopping-agent is its own container, own Render free web service (or equivalent), same image built from `services/shopping-agent/Dockerfile`, same code, same contracts.
- Problem (deployment-zero-cost doc, V): Render free tier = 750 instance-hours/workspace/month; only ONE service can be always-on for a month without exhausting hours. In Profile A, shopping-agent sleeps like every other non-gateway service (15 min idle, ~1 min wake, V) unless warmed.
- Profile A is kept buildable (own Dockerfile, own compose entry) so judges can run the "real microservices" topology locally via `docker compose`, per ADR-009 layout; it is NOT the hosted submission topology.

## 2. LLM free-tier use (per llm-cost-and-latency.md; re-verify before 2026-11-01)
- Primary provider for cart proposal: Gemini Flash-class (free tier, V exists for Flash/Flash-Lite models; exact RPM/RPD unpublished, read in AI Studio, I). Fallback 1: Groq `gpt-oss-120b` JSON mode (30 RPM, 1K RPD, 8K TPM, 200K TPD, V). Fallback 2 (always works, no LLM): deterministic form-driven cart (spec.md sec 7).
- Intent-fit: primary Gemini Flash-Lite, fallback Groq `gpt-oss-20b`; on exhaustion, skip straight to `NEEDS_BUYER_CONFIRMATION` (never PASS).
- Hard guards enforced in `llm-gateway`, not in this service: per-cart call caps (cart <= 2, fit <= 1), per-IP/session/global daily caps (70% of tightest provider daily cap), max input/output tokens, 8 s total wall budget, 1 provider retry (5xx/timeout only, never 429/402), circuit breaker (3 failures/60 s or any 402 or 2x 429/30 s -> open 120 s, half-open 1 probe).
- No payment method on any LLM provider account; Gemini project kept on a billing-free Google Cloud project (auto-upgrade risk if billing is ever linked, I — do not link). Free-tier content may train provider models (Gemini, V): only seeded catalog text and synthetic buyer intents are ever sent; never real PII.
- Kill switch `PS_SHOPPINGAGENT_LLM_ENABLED=false` (env) AND a DB flag (flip without redeploy) fail closed: `/propose` -> form; `/intent-fit` -> `NEEDS_BUYER_CONFIRMATION`. Gateway unreachable is treated identically to the kill switch being on.
- Caching: scripted demo inputs pre-warmed once before recording, stored `pinned=true`; cache hits always badge `source="cached"` on screen, never presented as live (spec.md sec 8). Cart cache is advisory-only — it never substitutes for `checkout`/`mandate` re-pricing and hard checks.

## 3. Health
- `GET /healthz` -> 200 `{"status":"ok"}`, no DB touch, no LLM call.
- `GET /readyz` -> 200 or 503 `{"db":"ok","config":"ok","gateway_breaker":"closed|open|half_open"}`. Readiness never makes a live LLM call (REQ-SA-018) — an open breaker is reported, not treated as not-ready, because the service can still serve `form`/`AI_PAUSED` results.
- Keep-warm: this service is warmed as part of the `ai` process via the same pinger that warms the process generally (UptimeRobot 5-min + cron-job.org backup, per deployment-zero-cost doc); do NOT add a second independent pinger for shopping-agent alone — Render's 750 h/month cap is shared per workspace, and pinging more than one always-on target exhausts it early (V math in deployment-zero-cost doc sec 4).
- `scripts/warmup.sh` includes a dry `/healthz` + one cached (not live) `/propose` call on scripted demo input before any recording session, so the first real click a judge makes is not the cold path.

## 4. Env (names only; values in platform env, never committed — full list in spec.md sec 10)
Deployment-relevant subset: `PS_SHOPPINGAGENT_LLM_ENABLED`, `PS_SHOPPINGAGENT_LLM_PROVIDER`, `PS_SHOPPINGAGENT_LLM_FALLBACK_PROVIDER`, `PS_SHOPPINGAGENT_LLM_MODEL_CART`, `PS_SHOPPINGAGENT_LLM_MODEL_CART_FALLBACK`, `PS_SHOPPINGAGENT_LLM_MODEL_FIT`, `PS_SHOPPINGAGENT_LLM_MODEL_FIT_FALLBACK`, `PS_SHOPPINGAGENT_GEMINI_API_KEY`, `PS_SHOPPINGAGENT_GROQ_API_KEY` (present only in the `ai` process env; never in `core`/`edge`/`paypal`), `PS_SHOPPINGAGENT_LLM_DAILY_CAP_PCT`, `PS_SHOPPINGAGENT_DB_URL` (scoped to `agent` schema only), `PS_SHOPPINGAGENT_CATALOG_BASE_URL`, `PS_SHOPPINGAGENT_MANDATE_BASE_URL`, `PS_SHOPPINGAGENT_AUDIT_EVENTS_URL`, `PS_SHOPPINGAGENT_INTERNAL_JWKS_URL`, `PS_SHOPPINGAGENT_SERVICE_AUDIENCE=shopping-agent`, `PS_SHOPPINGAGENT_LOG_LEVEL`.
- Startup check fails closed if any `PAYPAL_*` variable is present in this service's manifest (ADR-010; CI env-manifest test, mirrors the mandate pattern).
- CI env-manifest test: shopping-agent's manifest must not contain any `PAYPAL_*`, mandate HMAC keys, session/CSRF keys, or any other service's secret names.

## 5. Secrets
- `PS_SHOPPINGAGENT_GEMINI_API_KEY`, `PS_SHOPPINGAGENT_GROQ_API_KEY`: platform env of the `ai` process only (Render dashboard or equivalent), never in `.env.example` beyond placeholder names, never in git, never in logs (gateway strips Authorization-equivalent headers and provider keys from all log lines).
- `PS_SHOPPINGAGENT_DB_URL`: pooled Neon connection string scoped to the `agent` schema role (`svc_shopping_agent` or equivalent, ADR-004), no grants outside that schema.
- gitleaks pre-commit + CI full-history scan covers this service like every other (ADR, threat-model T13).

## 6. Rollback
- Stateless compute: this service holds no durable state outside `proposal_log`/`outbox` in its own `agent` schema and the shared `llm_cache`/`llm_calls` tables (schema placement is an open conflict, spec.md C2). Rollback = redeploy the previous image/commit (Render auto-deploy from Git, or manual `workflow_dispatch` with a prior SHA, per deployment-zero-cost doc CI section); no data migration to reverse for a code-only rollback.
- Schema (Alembic) changes to `agent` follow the same per-service migration discipline as every other service (ADR-004); a bad migration rolls back via the Alembic downgrade committed with the same PR, never a manual DB edit.
- LLM-side rollback: pinning `PS_SHOPPINGAGENT_LLM_MODEL_CART`/`PS_SHOPPINGAGENT_LLM_MODEL_FIT` to the last-known-good model id is a config-only change (no redeploy required if the platform supports live env edits); a bad prompt/model change is also reverted by restoring the previous `prompt_version` and `evals/baseline.json` and re-running the eval suite before re-promoting (llm-cost-and-latency.md sec 6 promotion rule: human-reviewed, never auto-promoted).
- Because the service never touches money state, a rollback here cannot leave an order, capture, or refund inconsistent — worst case is a worse (or no) cart proposal, degrading to the form fallback, which is always available and is never itself rolled back.

## 7. Known deployment conflicts / open items (service-map.md and ADR win; noted, not resolved here)
- Exact placement of `llm_calls`/`llm_cache` tables (schema `llm` shared by the `ai` process vs inside `agent`) is still open — see spec.md sec 14 C2; deployment behavior (one DB role vs two) depends on that decision and should be settled before the S2 exit gate (sprint-tasks.md).
- Whether Profile A inter-service calls for this service use public HTTPS URLs or private networking depends on the chosen host's capabilities (deployment-zero-cost doc sec 3(b), I — free hosts generally lack private networking, so the internal JWT is the real control, not network isolation).
- Gemini exact free RPM/RPD for the chosen model must be read in AI Studio and recorded in README before the model freeze (2026-11-05, llm-cost-and-latency.md sec 6); treat as unknown until then.
