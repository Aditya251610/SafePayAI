# api-gateway: PRD

Labels: V verified, VC vendor claim, I inference/assumption. Sources: 00-context-brief.md, architecture/{overview,service-map,adr,auth-gateway,threat-model,deployment-zero-cost}.md. Conflicts between those documents are recorded in spec.md section 14.

## 1. Role (one paragraph in bullets)
- Single public entry for the web app (buyer + merchant/operator UI). Nothing else is publicly routable (V design: service-map).
- Authenticates the human (gateway-owned session cookie, ADR-006), then mints a short-lived internal JWT per upstream call (EdDSA, `aud` = target service, `sub`, `role`, `jti`).
- Routes `/api/<svc>/*` to the owning service, rate limits, enforces CORS/CSRF/Origin, strips client-supplied identity headers, assigns request/trace ids.
- Offers a small read-only BFF (fan-out for UI screens) and a read-only `ops` surface for the freeze flag.
- Owns only the `gateway` schema: users (2-3 seeded + ephemeral demo buyers), sessions, signing-key metadata. No business data (V: service-map).
- Is on the money path only as a gate: if it is down the demo is down. It never decides money, never holds PayPal or LLM credentials, never writes audit.

## 2. Users and actors
| actor | how they reach the gateway | what they need |
|---|---|---|
| Buyer (judge or demo persona) | Browser, session cookie via "Start demo" | Frictionless entry, no signup, no PII; sign mandate, propose cart, pay, report problem, approve offer |
| Merchant (single shared demo login) | Browser, password login | Add tracking, case queue, review brief, override (creates NEW offer) |
| Operator (demo presenter / freeze owner) | Browser, password login | Demo clock, force late/lost, freeze/unfreeze refunds. Separate login from merchant (threat-model T9/T20) |
| Cron / pinger | HTTPS, shared secret header or plain GET | Keep warm, tick detector + reconcile |
| Other services | JWKS fetch only | Verify internal tokens |
| Developer / AI coding agent | OpenAPI + compose | Contract-first build (ADR-008) |
Reviewer is folded into merchant for v1 (see spec 14, C3).

## 3. Numbered requirements
Priority: P0 must ship by day-14 cut line, P1 before demo freeze, P2 only if time.

### Identity and session
- REQ-GW-001 (P0) `POST /api/auth/demo-session` creates an ephemeral buyer and a session; no PII collected; per-IP rate limit.
- REQ-GW-002 (P0) `POST /api/auth/login` for seeded merchant/operator (and optional seeded buyer persona) with argon2id verification and constant-time behaviour for unknown handles.
- REQ-GW-003 (P0) Session = opaque 256-bit id in a `__Host-` HttpOnly Secure SameSite=Lax cookie; DB stores only SHA-256 of the id; new id on every login (fixation).
- REQ-GW-004 (P0) Logout deletes the session row; `epoch` bump per user and global epoch invalidate sessions without redeploy.
- REQ-GW-005 (P0) `GET /api/auth/me` returns the Principal (no secrets) for the UI.
- REQ-GW-006 (P0) Session TTLs configurable (starting values I: buyer sliding 2 h / cap 8 h, merchant+operator 1 h).

### Request pipeline and trust
- REQ-GW-010 (P0) Assign `X-Request-Id` (uuid4, inbound ignored) and W3C `traceparent` (inbound accepted only if well-formed); echo `X-Request-Id` on every response, including errors.
- REQ-GW-011 (P0) Forward only an allowlist of request headers upstream; never forward `Cookie`, `Authorization` (browser), `X-User-*`, `X-Actor-*`, `X-Role*`, `X-Auth-*`, `X-Internal-*`, `X-Forwarded-*` (rewritten by gateway).
- REQ-GW-012 (P0) Default deny: any path/method not in the route table returns 404 (unknown) or 405 (known path, wrong method). `/internal/*` always 404.
- REQ-GW-013 (P0) Role check per route from the route table (buyer / merchant / operator); mismatch 403. Resource ownership is enforced by the owning service from `act.actor_id`, never from the body (threat-model T10).
- REQ-GW-014 (P0) Mint a per-upstream internal JWT (EdDSA, pinned alg, `aud` single service, `exp` <= 60 s by default, max 120 s per ADR-006, `jti`, `req`, `act`, `scope`, `kid`).
- REQ-GW-015 (P0) Publish `/.well-known/jwks.json` with current + previous public key; support `kid` rotation with overlap.
- REQ-GW-016 (P0) Never log tokens, cookies, `token`/`PayerID` query params, approval tokens in paths; log the route template instead of the raw path.

### CSRF, CORS, rate limit, headers
- REQ-GW-020 (P0) State-changing methods require allowlisted `Origin` (or `Referer` fallback) AND `X-CSRF-Token` bound to the session and purpose.
- REQ-GW-021 (P0) Sensitive purposes (`mandate_sign`, `approval_consent`, `mandate_revoke`, `offer_accept`, `order_confirm`) require a fresh single-use CSRF token (replay -> 403 `CSRF_REPLAYED`).
- REQ-GW-022 (P0) CORS: exact-origin allowlist from env, credentials true only with exact origin, never `*`, none on `/internal`. Preferred topology removes CORS (same-site rewrite, spec 4.3).
- REQ-GW-023 (P0) Per-principal (else per-IP) rate limits with 429 + `Retry-After`; stricter limits on auth, LLM-backed routes, and mandate/approval actions.
- REQ-GW-024 (P1) Global daily LLM-route budget counter with hard stop (gateway-side guard; provider caps remain the real backstop).
- REQ-GW-025 (P0) Security headers on all responses: CSP without inline script, `X-Content-Type-Options`, `Referrer-Policy: no-referrer`, `frame-ancestors 'none'`.
- REQ-GW-026 (P0) Body size cap and JSON content-type check on mutating routes; reject client-supplied money keys (`amount`, `currency`, `merchant`, `capture_id`, `price`, `total`) on routes where the client may only send ids/quantities (defence in depth for T22; owning service remains authoritative).

### Routing, resilience, errors
- REQ-GW-030 (P0) Proxy `/api/<svc>/*` to mandate, catalog, shopping-agent, checkout, tracking, resolution, audit (read) per route table. No route to paypal-adapter, triage-ai, or MCP.
- REQ-GW-031 (P0) Upstream client supports base URL OR in-process ASGI transport via config (Profile A and B are config, not code; overview section 8).
- REQ-GW-032 (P0) Timeouts per upstream call; retry ONLY idempotent calls (GET, or POST carrying an `Idempotency-Key`) on connect/timeout/502/503 with backoff, total budget under the web host's proxy timeout (Vercel proxied limit 120 s, V).
- REQ-GW-033 (P0) Pass `Idempotency-Key` through; require it (400 `IDEMPOTENCY_KEY_REQUIRED`) on money-affecting POSTs. Never retry a money POST without it.
- REQ-GW-034 (P0) Upstream 409 on refund/capture-class calls is passed through as "in progress", never retried by the gateway (V: PayPal concurrent same-Request-Id gives 409).
- REQ-GW-035 (P0) Uniform error body `{error, message, request_id}`; no stack traces, internal URLs, or versions (T21).
- REQ-GW-036 (P0) Cold-start handling: map connect timeouts to 503 `UPSTREAM_WAKING` with `Retry-After`; UI shows "waking server" state.
- REQ-GW-037 (P1) Validate any `approval_url` in checkout responses against an allowlisted host list before returning it to the browser.

### BFF, ops, health
- REQ-GW-040 (P1) Read-only BFF endpoints (buyer home, order detail, merchant queue) that fan out in parallel and degrade per section (partial results flagged), never writing.
- REQ-GW-041 (P0) `GET /api/ops/status` (freeze flag + demo mode + build info) and operator-only freeze toggle forwarded to the flag owner — resolved: **resolution** owns the flag (per resolution/spec.md C3) and pushes a mirror to paypal-adapter, fail-closed on both sides. Gateway never evaluates freeze itself for refunds (downstream enforces, threat-model section 10).
- REQ-GW-042 (P0) `PS_APIGATEWAY_MONEY_ROUTES_ENABLED=false` makes gateway return 503 `MONEY_ROUTES_DISABLED` on capture, offer accept, consent, confirm (gateway-level kill, separate from refund freeze).
- REQ-GW-043 (P0) `/healthz` (liveness, no DB), `/readyz` (DB + signing key loaded; optional deep upstream fan-out used only by warm-up).
- REQ-GW-044 (P1) `POST /api/ops/tick` (secret header) mints a system token (`sub=svc:poller`) and triggers tracking detector + resolution reconcile for cron use.
- REQ-GW-045 (P0) Demo-control routes exist only when `PS_APIGATEWAY_DEMO_MODE=true`, operator role only.

### Quality
- REQ-GW-050 (P0) Committed OpenAPI at `contracts/openapi/api-gateway.json`, CI fails on drift (ADR-008).
- REQ-GW-051 (P0) Env manifest (names only) and CI test proving no `PAYPAL_*`, `LLM_*`, `MANDATE_HMAC_KEY`, `APPROVAL_KEY` in the gateway env.
- REQ-GW-052 (P0) Structured JSON logs with request_id, trace_id, route template, status, latency, upstream, principal id hash; redaction unit test.

## 4. Non-goals
- No business rules, mandate checks, price math, policy, triage, or refund logic.
- No PayPal or LLM calls; no MCP proxying; no webhook receiver in v1 (design is poll-first, webhooks untested: I).
- No audit writes and no events (service-map: gateway emits/consumes none).
- No production-grade identity, MFA, SSO/IdP, password reset, or email. OIDC verifier interface is left as a seam only.
- No per-merchant accountability (single shared merchant login).
- No WAF, DDoS protection, or horizontal-scale rate limiting (single instance, in-memory limiter).
- No server-side response caching of business data.

## 5. Success metrics (no invented targets)
| metric | how measured | pass condition |
|---|---|---|
| Route-table coverage | test enumerates the app's routes vs table | every route has a role test and a 401/403 test; unlisted paths 404 |
| Spoofed-identity resistance | security suite (spec T19/T22 + header strip) | 0 requests reach a service carrying client-supplied identity headers |
| Secret hygiene | gitleaks full history, env manifest test | 0 findings; 0 forbidden vars |
| Contract drift | CI OpenAPI diff | 0 drift on main |
| Cold-start behaviour | warm-up and cold-run measured in week 1 and week 4 on the real host | measured and written in deployment.md; value unknown today (I) |
| Latency added by gateway | measured locally and hosted (p50/p95) | recorded, no target invented; budget decided after week-1 measurement |
| Demo robustness | 3 consecutive golden-path runs hosted, Profile B | all complete without manual restart |
| Mint latency / correctness | unit tests | all tokens verify at a service stub; wrong-aud/expired/alg-none rejected |

## 6. Risks
| # | risk | impact | mitigation | label |
|---|---|---|---|---|
| R1 | Single point of failure on the demo path | demo down | tiny stateless app, keep-warm, `/healthz` shallow, tested rollback | I |
| R2 | Cold start of gateway or upstream breaks first click | judge sees hang/timeout | pinger, warm-up script, `UPSTREAM_WAKING` UX, retries on idempotent calls only | V sleep ~1 min (Render docs), rest I |
| R3 | Cookie topology (Vercel vs Render domains) breaks SameSite=Lax session | login fails in hosted demo | Vercel rewrite so `/api/*` is same-site; decide in week 1 and test with a real PayPal return | I |
| R4 | Neon scale-to-zero (5 min idle, V) makes session lookup slow on first call | slow first request | accept ~1-2 s (VC); shallow healthz so pinger does not burn Neon hours | V/VC |
| R5 | Neon CU-h exhaustion from 24/7 DB pings | DB suspended | pinger hits `/healthz` only; deep checks only in windows | V math in deployment-zero-cost |
| R6 | Render 750 h/month is per workspace (V) | multiple always-on processes suspend all at month end | only edge pinged continuously; others woken on demand; fallback single-process host | V |
| R7 | In-memory rate limiter resets on restart / sleep | limits lapse | acknowledged; provider-side caps; global LLM budget | I |
| R8 | Return URL through our server untested | capture flow may fail at redirect | week-1 spike task (sprint-tasks GW-S1-08) | brief: untested |
| R9 | Over-claiming security | credibility loss | honest-claims list in spec 12; label demo-grade | V |
| R10 | AI-coded dependency risk (JWT, argon2, httpx) | supply chain | lockfile, review each dependency, pip-audit in CI | I |
| R11 | Ownership checks omitted in a downstream service | IDOR | gateway sends actor id only via token; compose IDOR matrix test across all routes | I |
| R12 | Contract mismatch with owning services (e.g. missing list endpoints) | BFF cannot be built | list in spec 14 C9; request additions early | I |
