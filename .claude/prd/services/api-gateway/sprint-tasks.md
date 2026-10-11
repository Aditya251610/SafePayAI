# api-gateway: sprint tasks

Labels: V verified, VC vendor claim, I inference/assumption. Aligned to `sprint-plan.md` (S1 Oct 10-16, S2 Oct 17-23 ending at the DAY-14 CUT LINE Oct 23, S3 Oct 24-30, S4 Oct 31-Nov 6 ending at FEATURE FREEZE Nov 6; code freeze Nov 9; submit Nov 10). Requirement ids from prd.md (REQ-GW-nnn); test ids from test-plan.md and test-strategy.md. Task ids `GW-Sn-nn`; the return-URL spike keeps the id `GW-S1-08` referenced by prd risk R8.
Standing rules (sprint-plan section 0): every feature task has a paired TEST and DEPLOY task in the same row; "done" = test in CI AND running on hosted Profile B. Deploy ritual = CI gate (ruff, pytest, contract diff, gitleaks, pip-audit, env-manifest) -> auto-deploy `edge` -> `curl --retry` on `/healthz` (V ~1 min wake) -> `/readyz` -> smoke (login -> mandate -> cart -> order create) -> `scripts/warmup` -> log in sprint log. Max 3 open PRs. Money-path PRs (anything on money routes) get deep human review; the rest rely on tests. No agent reads or prints `.env`.

## Week 1 (S1, Oct 10-16): skeleton, trust boundary, hosted, return URL
Goal: gateway deployed on `edge`, login and demo-session work, internal JWT verified by `libs/common`, proxy routes for mandate/catalog/checkout/audit, openapi committed, G1 hosted return-URL pass.
| ID | Feature task | Paired TEST task | Paired DEPLOY task |
|---|---|---|---|
| GW-S1-01 | Scaffold `services/api-gateway` (app/, tests/, migrations/, pyproject, `hosts/edge.py`), config with fail-fast + forbidden-var check (REQ-GW-051) | GW-U27, env-manifest test in CI; CI proves gitleaks catches a planted fake secret (shared S1-01) | Render service `edge` created from repo, no card; first green `/healthz` over HTTPS |
| GW-S1-02 | Contract first: OpenAPI stub `api-gateway.json`, error model, route table schema; internal JWT claim spec with `libs/common` owner (REQ-GW-050, ADR-008) | GW-K01, K02, K06 fixtures shared with every verifier | Mock upstreams in compose so web track does not block |
| GW-S1-03 | Request pipeline middleware: request id, traceparent, security headers, body limits, header strip, JSON logging with redaction (REQ-GW-010/011/016/025/026/052) | GW-U06-U08, U19, U24, U25, U28; GW-X08, X11 | Deployed; log line check on hosted `/healthz` + a 404 |
| GW-S1-04 | DB models + Alembic (`users`, `sessions`, `csrf_uses`, `signing_keys`, `settings`), `gateway_app` role, seed script (hashes made at seed time) | GW-I01, I02; Neon cross-schema denial | Migrations run from CI against Neon before deploy; roles verified on Neon (S1-04 shared) |
| GW-S1-05 | Sessions + demo-session + login/logout/me; argon2id; `__Host-` cookie; epochs (REQ-GW-001..006) | GW-U09-U12, I05-I07, X03, X15 | Cookie flags verified over real HTTPS on Render; staff passwords set in CI/shell for seed only |
| GW-S1-06 | Token minting + JWKS + keys loader (EdDSA, kid, previous key) (REQ-GW-014/015) | GW-U01-U05, K07, X02 (stub verifier: wrong aud, expired, alg=none) | Signing key in Render env only; JWKS reachable from `core` |
| GW-S1-07 | Route table + generic proxy + upstream client (`http` / `inprocess`), timeouts, retry rules, `UPSTREAM_WAKING` mapping, idempotency enforcement; routes for mandate, catalog, checkout (carts/confirm/capture/orders), audit read (REQ-GW-012/013/030-036) | GW-U20-U23, K04, K08, I08, I09, I11-I13, I20 | Deployed in `edge` with `core` URL; smoke through gateway to mandate and catalog |
| GW-S1-08 | SPIKE G1 hosted (R8, C16): Vercel rewrite topology + cookie SameSite=Lax + real PayPal return to the static web route -> `POST /api/checkout/orders/{id}/capture` path; confirm sandbox `approval_url` host for the allowlist; record `TRUSTED_PROXY_COUNT`; measure cold start and gateway-added latency (p50/p95) | Manual real-click run recorded in `docs/gates.md` (V/I labelled); GW-E05 with the double | Same on hosted Render/Vercel on Day 3; if cookie fails: R3 open, escalate same day |
| GW-S1-09 | CSRF (general + single-use purposes), Origin check, CORS allowlist, `GET /api/auth/csrf` (REQ-GW-020/021/022) | GW-U13-U16, I03, X04, X05 | Deployed; `PS_APIGATEWAY_FRONTEND_ORIGINS` set to hosted web origin |
| GW-S1-10 | Rate limiter (classes) + health endpoints (`/healthz`, `/readyz`) (REQ-GW-023/043) | GW-U17, X06 (spoofed XFF) | UptimeRobot 5-min on `/healthz` of `edge` only (G6, V interval); cron-job.org backup |
Exit (week): login + demo-session + JWKS + proxy to mandate/catalog/checkout live on hosted edge; cross-service token verify (I1 integration) accepted by core stubs; G1 recorded; OpenAPI committed; CI green; 3 consecutive S1 demo runs hosted. Weekly demo W1 (Oct 16): label check, no secrets on screen.

## Week 2 (S2, Oct 17-23): money-route hardening, agent, ops; DAY-14 CUT LINE Oct 23
Goal: everything the cut-line path needs goes through the gateway cleanly; BFF only if endpoints exist.
| ID | Feature task | Paired TEST task | Paired DEPLOY task |
|---|---|---|---|
| GW-S2-01 | Single-use CSRF on mandate sign, revoke, confirm; `Idempotency-Key` required on money POSTs; `PS_APIGATEWAY_MONEY_ROUTES_ENABLED` brake (REQ-GW-021/033/042) | GW-U14, U21, I03, I15, X04 | Deployed; brake toggle rehearsed once (restart behavior noted: I) |
| GW-S2-02 | Upstream 409 pass-through (capture/accept/consent), mapped 422 pass-through (REQ-GW-034, V basis S19-S21) | GW-I12, I13 | Smoke includes a forced-409 stub path in staging compose |
| GW-S2-03 | Proxy routes for shopping-agent `/api/agent/propose` with `llm` class + global LLM counter (REQ-GW-024, P1) | GW-U18, X10 | Deployed; counter value set from Gemini/Groq limits (V Groq 30 RPM; Gemini quotas read in AI Studio) |
| GW-S2-04 | `approval_url` host validation (REQ-GW-037) using G1 result | GW-U26, X16 | Allowlist env set on hosted `edge` |
| GW-S2-05 | `GET /api/ops/status`; operator login; `POST /api/ops/freeze` forward with owner stub (REQ-GW-041); depends on C6 decision (resolution vs adapter owns flag) | GW-I16, X03 (operator separate from merchant) | Deployed; owner target agreed before Oct 20 (I) |
| GW-S2-06 | IDOR + role matrix across all routes live at cut line (mandate, cart, order, receipt) (REQ-GW-013) | GW-I09, I10, X06; joint T10 suite (sprint S2 gate) | Run in compose and against hosted staging |
| GW-S2-07 | Cold-start UX contract: `UPSTREAM_WAKING` body + `Retry-After`; `scripts/warmup` gateway part (`/readyz?deep=true` restricted) | GW-U23, I20, E04 | Warm-up + one 12 h-idle cold run before the cut line (cut-line item 1) |
| GW-S2-08 | Key rotation procedure + drill (REQ-GW-015) | GW-I24, K07 | Drill on hosted env once; record in runbook |
| GW-S2-09 (P1, cut-eligible) | BFF read endpoints `buyer-home`, `orders/{id}`, `merchant-queue` (REQ-GW-040); needs C9 list endpoints from mandate/checkout | GW-I19 | Deploy only if owners shipped list endpoints; else drop `buyer-home` and let UI use direct reads |
Cut-line checklist for the gateway (supports sprint-plan DAY-14 CUT LINE, all required): hosted path sign mandate -> cart -> checks -> PayPal order -> sandbox approve -> return URL -> capture -> receipt 5 consecutive clean runs, one after >= 12 h idle; revoke blocks new cart; CI green, gitleaks clean, IDOR green; raw capture recorded.
If the cut line is at risk: stop GW-S2-09, GW-S2-03 (agent proxy stays minimal), and any polish; spend Oct 24-25 only on the failing path.
Weekly demo W2 (Oct 23): 5 timed runs; one with LLM failing (UI manual cart); one over-cap block.

## Week 3 (S3, Oct 24-30): tracking/resolution/ops routes, tick
Goal: hero loop reachable through the gateway on hosted demo; no new gateway concepts, only routes and ops.
| ID | Feature task | Paired TEST task | Paired DEPLOY task |
|---|---|---|---|
| GW-S3-01 | Tracking routes: shipments (M), shipment read, demo clock advance + force (O, `PS_APIGATEWAY_DEMO_MODE` only) (REQ-GW-045) | GW-I14 (no tracker status mutation route), I17, X08; joint T9 | Deployed; `PS_APIGATEWAY_DEMO_MODE=true` on demo env only; clock panel behind operator login |
| GW-S3-02 | Resolution routes: report (llm class), cases read (own/list by role), offers accept (single-use `offer_accept`), approvals consent (single-use `approval_consent`, token path never logged), merchant-action | GW-U14, U25, X14, I09, I10, I12; joint T1-T3 concurrency/replay through gateway (20 parallel accepts -> one result) | Deployed; consent route log template verified on hosted logs |
| GW-S3-03 | `POST /api/ops/tick` with `X-Tick-Secret`, system token `svc:poller` (REQ-GW-044) | GW-I18; idempotency of downstream detector/reconcile calls | GitHub Actions scheduled `tick` workflow + `keepwarm.yml`; secret in Actions secrets; pinger stays on `edge` only (G6) |
| GW-S3-04 | Audit read routes complete (entries, verify) and BFF `orders/{id}` including shipment/case/audit flag (if BFF kept) | GW-I19, I22 | Deployed; UI audit verify button works through gateway |
| GW-S3-05 | Chaos through gateway in compose: Postgres refused (C12), mandate down (C14), catalog down (C15), audit down (C16), flag store unreachable (C17), sleeping consumer (C22) | GW-I20-I22; chaos subset green | Nightly compose chaos job |
| GW-S3-06 | Gateway-level abuse checks on LLM routes and free-text routes (body cap, 429, budget stop) | GW-X10, X11 | Deployed; limits tuned from week-2 measurements (I) |
Exit (week): full story reachable through the gateway 5 consecutive hosted runs (shared S3 exit); concurrency suite green in CI; runbook entries for reset/warm-up/token and gateway brakes written.
If behind at Day 19: cut GW-S3-04 BFF parts and merchant-action proxy first (sprint cut list items 3-8); protect GW-S3-01..03.

## Week 4 (S4, Oct 31-Nov 6): hardening, measurement, soak; FEATURE FREEZE Nov 6
Goal: no new routes after Nov 6. Prove behavior, record numbers, finish docs.
| ID | Feature task | Paired TEST task | Paired DEPLOY task |
|---|---|---|---|
| GW-S4-01 | Hardening: tune rate limits from load smoke; admin/ops routes denied without role/secret; error pages; `Retry-After` semantics; security headers re-check | GW-X03-X07, X11, X15; perf smoke P1-P3, record gateway-added p50/p95 hosted (no target invented) | Deployed; limits recorded in README table as "starting values, demo-grade" |
| GW-S4-02 | Final key rotation drill and rotation of any dev values (HMAC/JWT/CSRF/tick/seed); confirm no secret in Vercel client bundle | GW-I24, X09, X14; full-history gitleaks | Platform env updated; services redeployed in order (gateway last) |
| GW-S4-03 | Cold-start measurement on real host (after >= 24 h idle and after ~15 min idle) and token-expiry paths; fill the values into deployment.md (currently unknown) | GW-E04; hosted observation log | Update deployment.md sections 2 and 11; decide single-process fallback (`hosts/all.py`) if flake > 1 in 10 runs (G6) |
| GW-S4-04 | Profile A parity: compose with `UPSTREAM_MODE=http`; hosted Profile B with `http`; fallback `inprocess` rehearsal | GW-K09 matrix, compose e2e on both | README states "same services, co-located for the free tier" |
| GW-S4-05 | Docs: gateway README (honest claims list from spec 12, demo-grade labels, env names), OpenAPI final, `docs/known-issues.md` entries | Forbidden-claims grep (T25) over gateway strings; fresh-clone `docker compose up` run | Docs in repo |
| GW-S4-06 | Soak support: 10 consecutive hosted runs with zero manual fixes, one after 24 h idle; scheduled smoke every 6 h (continues to Dec 21) | Soak script results log; any gateway failure resets the count | `keepwarm.yml` + smoke workflow live; Nov 1 free-tier re-check done (Render hours, Neon CU-h, Vercel terms) |
Exit (week): freeze declared Nov 6 end of day; soak passed; all GW tasks have test + hosted pass; gateway DoD in test-plan section 12 met.
After freeze (Nov 7-10): sev-1/2 fixes and config hotfixes only (e.g. `PS_APIGATEWAY_FRONTEND_ORIGINS`, `PS_APIGATEWAY_MONEY_ROUTES_ENABLED`, key swap); code freeze Nov 9 tag `v1.0-submission`; warm-up and smoke before recording; keep demo alive through Dec 21 (smoke every 6 h, dated TODOs for free-tier changes).

## What to cut first (gateway scope, cut from the top)
1. GW-S2-09 / GW-S3-04 BFF (REQ-GW-040): UI uses direct proxied reads (this also happens automatically if C9 list endpoints are not delivered).
2. `GET /readyz?deep=true` fan-out (REQ-GW-043 part): `scripts/warmup` hits each service `/healthz` directly.
3. Global LLM budget counter (REQ-GW-024, GW-S2-03/S3-06 part): rely on per-session `llm` rate class and provider caps (Groq/Gemini) as the real backstop.
4. `approval_url` host allowlist (REQ-GW-037, P1): checkout is the sole source of the URL; keep only the scheme check. Not recommended if time allows (cheap).
5. `POST /api/ops/tick` (REQ-GW-044): drive the detector with the demo clock panel and an in-process loop in `core`; cron-driven tick is a backup (sprint-plan S3-01 already has both).
6. `merchant-action` proxy route (follows sprint cut item 3).
7. Optional buyer persona login and Sentry.
Never cut: session + CSRF/Origin, header strip, internal JWT mint + JWKS, route table default deny, role checks, idempotency enforcement, `UPSTREAM_WAKING` handling, `PS_APIGATEWAY_MONEY_ROUTES_ENABLED` brake, log redaction, env-manifest test, health endpoints, gitleaks, OpenAPI drift gate.

## Dependencies and open decisions to close early
| item | needed by | owner |
|---|---|---|
| C1 JWKS vs static `trusted_issuers` fallback agreed with `libs/common` | Oct 12 (I1 integration, Day 3-4) | libs/common author |
| Cookie topology (Vercel rewrite) works | Oct 12 (GW-S1-08) | human + gateway agent |
| C6 freeze-flag owner | Oct 20 | resolution + paypal-adapter authors |
| C9 list endpoints for BFF | Oct 17 | mandate + checkout authors |
| Env prefix scheme `PS_APIGATEWAY_*` confirmed (agent-context-map says I) | Oct 11 | contracts/CI owner |
| Operator role added to service-map (C3) | Oct 12 | architecture owner |
| `approval_url` host (C16) | Oct 12 | GW-S1-08 |
| Numbers: timeouts, TTL, rate limits | after week-1 measurement | gateway agent (no numbers invented in docs) |
