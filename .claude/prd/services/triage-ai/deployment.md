# triage-ai: Deployment

Labels: V verified (read today), VC vendor/secondary, I inference. Source: architecture/deployment-zero-cost.md, llm-cost-and-latency.md, ADR-005, ADR-009. Monorepo note (I, locked by task brief): code at `services/triage-ai/` inside the single public GitHub repo; deploy artifacts (Dockerfile, host mount) live alongside it per ADR-009 layout, not in a separate repo.

## 1. Profile B (demo placement — primary)
- triage-ai is co-hosted inside the `ai` process (Render free web service), per overview/PRD section 1 and ADR-005's "Profile B co-location". The `ai` process also hosts `shopping-agent`; both import the shared `llm-gateway` package in-process (spec.md section 14 #1 — no service-to-service hop, no extra cold start).
- Mount: `hosts/ai.py` per ADR-009 layout mounts triage-ai's FastAPI app as a sub-application (or ASGI mount) alongside shopping-agent's. Routes stay `/classify`, `/draft`, `/brief`, `/healthz`, `/readyz`, `/health`, `/health/deep` under the `ai` process's base path.
- Host: Render free web service (750 instance-h/month per workspace, no rollover, suspended when exhausted — V, deployment-zero-cost.md section 1). Sleeps after 15 min idle, ~1 min cold start (V). The `ai` process is one of up to 4 Profile B processes (edge/core/ai/paypal); deployment-zero-cost.md section 4 math shows only ONE process can be always-on within the 750h cap, so `ai` is expected to sleep and be woken by the gateway's warm-up fan-out, not pinged 24/7.
- DB: schema `triage` on the single shared Neon Postgres free instance (ADR-004); role scoped to `triage` only, no grant on `mandate/checkout/resolution/paypal/...`. Neon scales to zero after 5 min idle (V); resume latency ~1-2s is I. Do not add a dedicated DB keep-warm ping for `triage`'s own data — Neon CU-h budget (400h at 0.25 CU) is shared across the whole project and 24/7 pinging exhausts it in ~16 days (V math, deployment-zero-cost.md section 4).
- Keep-warm: no dedicated pinger on `ai`/triage-ai by default (hours budget reserved for `edge`, per G6 decision in sprint-plan.md). Before any demo/recording, `scripts/warmup.sh` hits `/health` on every Profile B process in parallel including `ai`, then runs one dry proposal/classify call, then waits for 200 before recording (deployment-zero-cost.md section 4).

## 2. Profile A (separated-services placement — architecture/local)
- triage-ai runs as its own FastAPI app with its own Dockerfile (`services/triage-ai/Dockerfile`), started via `docker-compose.yml` as an independent container, matching ADR-009's "containers deployable to any host" rule and ADR-001's "build (b)-ready code" recommendation.
- In Profile A, the same code imports `llm-gateway` as a package in-process — the package/service boundary is a code-import decision, not a network one, so Profile A does NOT turn `llm-gateway` into a separate container; it stays inside triage-ai's (and shopping-agent's) process in both profiles (spec.md section 14 #1).
- Local dev: `docker compose up` runs all 10 services + web + Postgres; PayPal is a double, LLM is a stub by default (test-strategy.md section 7) — triage-ai in Profile A local dev does not need real provider keys unless running the live eval suite.
- Profile A is shown in architecture docs + judge-runnable compose; the submitted hosted demo uses Profile B (deployment-zero-cost.md section 3b).

## 3. Free LLM use
- Primary: Groq `gpt-oss-20b` for triage classification (fast, 30 RPM — V, llm-cost-and-latency.md section 1), chosen over Gemini for this task because speed matters on stage (L1 latency class, <2s target).
- Fallback 1: Gemini Flash-Lite.
- Fallback 2 (always works, no LLM): keyword rules -> `HUMAN_REVIEW` (deterministic, REQ-TA-003).
- Draft (`/draft`) and brief (`/brief`) use Gemini Flash primary, Groq `gpt-oss-120b` fallback 1, static templates / fact-template fallback 2 (llm-cost-and-latency.md section 1).
- Exact free-tier RPM/RPD for the chosen Gemini models are NOT published and must be read in AI Studio before freeze (I, open item in both llm-cost-and-latency.md and spec.md section 15).
- Guards enforced by `llm-gateway` (not triage-ai itself): max 6 LLM calls per `case_id` lifetime across all AI tasks, of which triage-ai uses at most 3 (classify, draft, brief), no retries beyond 1 (REQ-TA-037, llm-cost-and-latency.md section 2); per-IP and global daily caps at 70% of the tightest provider cap; circuit breaker opens after 3 failures in 60s or any 402 or 2x 429 in 30s.
- Gemini free-tier content is used to improve Google's products (V) — triage-ai must only ever send seeded/synthetic buyer text and carrier notes, never real PII (prd.md risk table, llm-cost-and-latency.md section 0).
- No billing account on the Gemini project (keeps it on free tier; linking billing risks auto-upgrade to paid, V, llm-cost-and-latency.md section 8). No payment method on Groq/OpenRouter accounts used.

## 4. Environment variables (names only, no values — triage-ai specific, from spec.md section 12)
| name | purpose |
|---|---|
| `PS_TRIAGEAI_LLM_ENABLED` | kill switch (env + DB flag); off -> every triage-ai endpoint returns its deterministic fallback (REQ-TA-033) |
| `PS_TRIAGEAI_MIN_CONFIDENCE` | route threshold, UNVALIDATED (default `0.7`, config not code) |
| `PS_TRIAGEAI_MAX_TEXT_CHARS` | per-untrusted-field cap before sending to model (default `1000`) |
| `PS_TRIAGEAI_PROMPT_VERSION` | prompt id stamped on every call (default `v1`) |
| `PS_TRIAGEAI_TIMEOUT_CLASSIFY_S`, `PS_TRIAGEAI_TIMEOUT_DRAFT_S`, `PS_TRIAGEAI_TIMEOUT_BRIEF_S` | per-call timeouts (defaults `4`/`6`/`10`) |
| `PS_TRIAGEAI_STALE_WINDOW_HOURS` | rule threshold for `CLAIM_LOST_BUT_IN_TRANSIT_RECENT`; must be set before sprint 3 |
| `PS_TRIAGEAI_MAX_CALLS_PER_CASE` | shared cap, enforced in gateway (default `6`) |
| `PS_TRIAGEAI_CACHE_TTL_HOURS` | non-pinned cache TTL (default `24`) |
| `PS_TRIAGEAI_DEBUG_LOG_PROMPTS` | log raw prompts, synthetic demo only (default `false`) |
| `PS_TRIAGEAI_LLM_PROVIDER_PRIMARY`, `PS_TRIAGEAI_LLM_PROVIDER_FALLBACK`, `PS_TRIAGEAI_LLM_MODEL_TRIAGE_*` | gateway routing config, not code |
| `PS_TRIAGEAI_GEMINI_API_KEY`, `PS_TRIAGEAI_GROQ_API_KEY` | provider secrets, read by `llm-gateway` inside the `ai` process env only — never in triage-ai's own env block if the process boundary ever splits |
| `PS_TRIAGEAI_DATABASE_URL` | secret; role limited to schema `triage` |
| `PS_TRIAGEAI_INTERNAL_JWKS_URL`, `PS_TRIAGEAI_INTERNAL_JWT_AUDIENCE` (`triage-ai`), `PS_TRIAGEAI_INTERNAL_ALLOWED_CALLERS` (`resolution`) | auth |
| `PS_TRIAGEAI_AUDIT_PUSH_URL`, `PS_TRIAGEAI_INTERNAL_EVENT_HMAC_KEY` | outbox relay to audit, secret |
| `PS_TRIAGEAI_SERVICE_NAME`, `PS_TRIAGEAI_LOG_LEVEL`, `PS_TRIAGEAI_ENV` | standard |
No secret values appear in the repo, `.env.example`, or any doc (brief section 5, spec.md section 12). Names above are `PS_TRIAGEAI_*`-prefixed per the confirmed platform-wide env-var naming convention (user decision, 2026-10-10); this applies even to the LLM provider/key names that are physically read inside the shared `ai` process, matching the pattern already used by shopping-agent (each co-located service keeps its own prefixed names rather than sharing bare `LLM_*`/`GEMINI_API_KEY` names).

## 5. Health and warm-up
- `/healthz`: liveness only, no deps, always 200 if process up.
- `/readyz`: checks `triage` schema DB connectivity; 503 `NOT_READY` if down (used by deploy health-gate per sprint-plan.md deploy ritual: `curl --retry` on readiness, accounting for ~1 min Render wake).
- `/health`, `/health/deep`: aliases (resolution/spec.md conflict C8 pattern applied consistently here); `/health/deep` additionally reports kill-switch state and breaker state for the `llm-gateway` package without making a live model call, so warm-up scripts can confirm AI readiness without spending quota.
- `scripts/warmup.sh` hits every Profile B process's `/health` in parallel, then `/health/deep`, then one full dry run (deployment-zero-cost.md section 4) before any recording — triage-ai must respond within this window or the recording is delayed, not faked.

## 6. Rollback
- Deploy ritual (sprint-plan.md, standing rule): CI green (ruff, pytest, contract diff, gitleaks, pip-audit) -> auto-deploy `main` to the `ai` Render process -> health gate on `/readyz` (retries for ~1 min wake) -> smoke test -> `scripts/warmup` -> record result in sprint log. A failing health gate blocks promotion; the previous Render deploy remains live (Render serves the last successful deploy until a new one passes).
- Manual rollback: `workflow_dispatch` with a target commit SHA re-deploys that SHA to the `ai` process (sprint-plan.md S1-04/S4-02 pattern — no dedicated triage-ai rollback script exists beyond this generic one; I, inferred from the shared deploy ritual, no triage-ai-specific rollback procedure is documented elsewhere).
- Contract changes to `/classify`, `/draft`, `/brief` are additive-only post-freeze (ADR-008); a breaking change requires a version bump and a "contract PR" reviewed by the human (sprint-plan.md section 9) before `resolution` (the only caller) can adapt — rollback of a bad contract change means reverting both triage-ai and, if already deployed, `resolution`'s client together.
- Kill-switch is the fast "rollback" for AI behavior, not a deploy: flipping `PS_TRIAGEAI_LLM_ENABLED=false` (env or DB flag, no redeploy) immediately forces every endpoint to its deterministic fallback (REQ-TA-033) — this is the preferred first response to a bad model/prompt change discovered live, before a code rollback.
- Model/prompt rollback: `PS_TRIAGEAI_PROMPT_VERSION` and `PS_TRIAGEAI_LLM_MODEL_TRIAGE_*` are config, not code (llm-cost-and-latency.md section 1) — reverting to a prior prompt/model is a config change in the platform env, redeployed via the same CI gate, not a git revert.
