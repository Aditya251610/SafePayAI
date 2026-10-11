# api-gateway: test plan

Labels: V verified, VC vendor claim, I inference/our heuristic. References test IDs from `/home/harsh/Projects/artiq/.claude/prd/test-strategy.md`: T1-T26 (security), C1-C24 (chaos), S01-S25 (PayPal spike regression), E1-E12 (Playwright), L1-L8 (layers). Gateway-local IDs: GW-U (unit), GW-K (contract), GW-I (integration), GW-E (e2e), GW-X (security). Numeric thresholds are our own (I). Sandbox only; the gateway holds no PayPal or LLM credentials, so no live PayPal or LLM call is made by this suite.

## 1. Scope and approach
- The gateway has no business logic. Tests prove: identity and session correctness, header trust boundary, token minting, route table default-deny, CSRF/CORS/rate limits, idempotent/non-idempotent retry rules, error model, cold-start behavior, and honest labelling.
- Upstreams are fakes generated from committed OpenAPI (test-strategy L3) or in-process ASGI stubs. Spike-verified PayPal facts matter only as pass-through behavior (409, 422 mapping, no tracker mutation route, `custom_id` surviving), not as PayPal calls.
- Profile parity: the same contract suite runs with `UPSTREAM_MODE=http` (Profile A) and `inprocess` (Profile B/all).

## 2. L1 unit cases
| ID | Case | Expected |
|---|---|---|
| GW-U01 | Mint token: claims `iss=api-gateway`, `sub`, single `aud`, `iat`, `exp`, `jti`, `req`, `act`, `role`, `scope`, `kid`, `sid` (hash only) | verifies with JWKS public key at a service stub |
| GW-U02 | TTL: default 60 s; configured >120 s is clamped/refused at startup (ADR-006 max 120) | startup error or clamp |
| GW-U03 | Verifier stub rejects wrong `aud`, expired (beyond skew <= 5 s), `alg=none`, alg switch (HS256 with public key as secret), unknown `kid`, tampered payload | all rejected (feeds T19) |
| GW-U04 | Token never reused across `aud` (two upstream calls -> two tokens, different `jti`) | pass |
| GW-U05 | `jti` unique over N mints | no duplicates |
| GW-U06 | Header filter: forwards only allowlist; drops `Cookie`, inbound `Authorization`, `X-User-*`, `X-Actor-*`, `X-Role*`, `X-Auth-*`, `X-Internal-*`, `X-Forwarded-*`, `Forwarded`, `X-Real-IP` (case-insensitive, duplicate headers, CRLF attempts) | none reach upstream stub |
| GW-U07 | `X-Request-Id`: inbound ignored, new uuid4 echoed on success and error; `traceparent` accepted only if W3C-valid (all-zero trace id rejected) | pass |
| GW-U08 | Response filter: drops upstream `Set-Cookie`, `Server`, `Location`; keeps `Content-Type`, `Cache-Control`, `Retry-After`, `ETag` | pass |
| GW-U09 | Session cookie value: 256-bit random; DB stores only SHA-256; new sid on each login; old presented sid deleted | pass |
| GW-U10 | Session validity: expired, user epoch bump, `global_epoch` bump, disabled user -> invalid (401 + expired cookie) | pass |
| GW-U11 | Sliding expiry capped (buyer cap, staff fixed); `last_seen_at` write throttled to once/min | pass |
| GW-U12 | argon2id verify; unknown handle takes the dummy-hash path (timing within same order of magnitude, not exact: I); identical error for unknown handle vs bad password | pass |
| GW-U13 | CSRF token: MAC bound to `sid_hash`+purpose+ts+jti; wrong purpose, expired, other session, truncated -> `CSRF_FAILED`; constant-time compare used | pass |
| GW-U14 | Single-use purposes (`mandate_sign`, `approval_consent`, `mandate_revoke`, `offer_accept`, `order_confirm`, `ops_freeze`): second use -> `CSRF_REPLAYED`; `general` reusable until expiry | pass |
| GW-U15 | Origin check: allowlisted Origin passes; missing Origin falls back to Referer; absent both on mutating -> `ORIGIN_NOT_ALLOWED`; `null` origin rejected; look-alike host rejected | pass |
| GW-U16 | CORS: exact origin gets `Allow-Credentials: true`; unknown origin gets no CORS headers; never `*` | pass |
| GW-U17 | Rate limiter per class, key = session else IP; 429 + `Retry-After`; window resets; `TRUSTED_PROXY_COUNT` respected (spoofed `X-Forwarded-For` beyond trusted hops ignored) | pass |
| GW-U18 | Global LLM counter hard stop -> `LLM_BUDGET_EXHAUSTED` | pass |
| GW-U19 | Body guard: size cap -> 413; non-JSON -> 415; forbidden money keys (`amount`, `currency`, `merchant`, `capture_id`, `price`, `total`) at any nesting depth on id/quantity-only routes -> `CLIENT_MONEY_FIELD_REJECTED` | pass; not applied on routes whose owner schema legitimately contains those fields |
| GW-U20 | Route table: every entry has method, path, upstream, roles, rate class, CSRF purpose, idempotency flag; `PS_APIGATEWAY_DEMO_MODE` routes absent from table when false | pass |
| GW-U21 | Idempotency rule: money POST without `Idempotency-Key` -> 400 `IDEMPOTENCY_KEY_REQUIRED` before any upstream call | upstream stub receives 0 calls |
| GW-U22 | Retry policy: GET and keyed POST retry on connect error/timeout/502/503 within total budget; POST without key never; 409 never; 4xx never | call counts asserted |
| GW-U23 | Waking mapping: connect timeout -> 503 `UPSTREAM_WAKING` + `Retry-After`; read timeout -> 504; non-JSON upstream -> 502 | pass |
| GW-U24 | Error model: every error has `{error,message,request_id}`; no stack trace, internal URL, version, SQL text (T21) | pass |
| GW-U25 | Log redaction: cookies, `Authorization`, tokens, CSRF tokens, `token`/`PayerID`/`state` query params, approval token in path never appear; log uses route template and no query string (T26, REQ-GW-016, REQ-GW-052) | grep over captured logs |
| GW-U26 | `approval_url` host allowlist: allowed host passes; look-alike host, userinfo trick (`allowed.com@evil.com`), http scheme, IP literal rejected (REQ-GW-037) | pass |
| GW-U27 | Config fail-fast: missing required env, forbidden vars (`PAYPAL_*`, `LLM_*`, `MANDATE_HMAC_KEY`, `APPROVAL_KEY`) present -> startup refuses (REQ-GW-051) | pass |
| GW-U28 | Hypothesis property tests: header filter never emits a name from the deny families for any generated header set; route matcher never routes `/internal/*` | no counterexample |

## 3. L2 contract cases
| ID | Case | Expected |
|---|---|---|
| GW-K01 | Generated OpenAPI equals committed `contracts/openapi/api-gateway.json` (CI drift, ADR-008) | no diff |
| GW-K02 | openapi-diff vs main: removal/narrowing fails without version bump | gate |
| GW-K03 | Schemathesis against the gateway app (stubbed upstreams): no 5xx on generated input, responses match schema, unknown fields rejected where declared | pass (T21 negative) |
| GW-K04 | Route enumeration: every FastAPI route is in the route table and vice versa; every route has a role test and a 401/403 test (prd metric) | 100% |
| GW-K05 | Consumer-driven: generated clients in `libs/clients` for each upstream exercised via ASGI against provider apps; provider PRs verify | pass |
| GW-K06 | Internal JWT contract fixtures consumed by `libs/common` verifier (same fixtures used by every service): valid, wrong-aud, expired, alg-none, unknown-kid | all services agree |
| GW-K07 | JWKS document shape (OKP/Ed25519, `kid`, `alg`), current + previous key during overlap | pass |
| GW-K08 | Upstream error pass-through: JSON error bodies keep status, gateway `request_id` replaces upstream's | pass |
| GW-K09 | Profile parity: GW-K01..K08 identical under `UPSTREAM_MODE=http` and `inprocess` | same results |

## 4. L3 integration (real Postgres, ephemeral schema, role `gateway_app` recreated)
| ID | Case | Expected |
|---|---|---|
| GW-I01 | Alembic upgrade from empty and from previous release; downgrade of last expand step; seed script idempotent | pass |
| GW-I02 | Role grants: `gateway_app` can use schema `gateway`, cannot SELECT other schemas (ADR-004) | denied |
| GW-I03 | `csrf_uses` unique violation on concurrent reuse (N=20 parallel same token) -> exactly one success, rest `CSRF_REPLAYED` | pass |
| GW-I04 | Concurrent demo-session creation respects `MAX_EPHEMERAL_BUYERS`; lazy purge removes expired sessions and ephemeral buyers | pass |
| GW-I05 | Login -> me -> logout -> me (401); epoch bump kills all sessions without redeploy | pass |
| GW-I06 | Fixation: pre-set cookie before login is deleted, new sid issued | pass |
| GW-I07 | Cookie flags over test TLS: `__Host-` prefix, Secure, HttpOnly, SameSite=Lax, Path=/, no Domain | pass (T19) |
| GW-I08 | Forged-identity requests (client sends `X-User-Id`, `X-Actor-Role: operator`, `Authorization: Bearer ...`) reach upstream stub with none of them and with the session's real `act` | pass (T19) |
| GW-I09 | Role matrix auto-built from route table: buyer on merchant/operator routes -> 403; anon on authed routes -> 401; list cases as buyer -> 403 | pass |
| GW-I10 | IDOR enumeration (T10, joint with owners): buyer B calling buyer A's ids through every proxied route; gateway sends only B's `act.actor_id`; compose stubs enforce ownership | no 200 with A's data |
| GW-I11 | Client money fields: `amount`/`currency`/`merchant` in cart/capture bodies rejected by gateway; with the guard disabled in a test, owner stub ignores them (T22 defence in depth) | pass |
| GW-I12 | Upstream 409 on capture/accept/consent returned as 409, upstream call count == 1 (V: concurrent same Request-Id gives one 201 + one 409; maps to S21) | pass |
| GW-I13 | Upstream 422 with mapped code (REFUND_AMOUNT_EXCEEDED / DUPLICATE_INVOICE_ID analogues, S19/S20) passes through; raw PayPal text never appears | pass |
| GW-I14 | No route exists for tracker status mutation; `PATCH /api/tracking/...status` -> 404/405 (S13/S14: PayPal allows only CANCELLED, V) | pass |
| GW-I15 | `PS_APIGATEWAY_MONEY_ROUTES_ENABLED=false`: confirm, capture, offer accept, consent -> 503 `MONEY_ROUTES_DISABLED`, reads and mandate sign unaffected, upstream call count 0 | pass |
| GW-I16 | Freeze status: owner stub down -> `/api/ops/status` shows `unknown`; merchant calling freeze -> 403; unfreeze without reason -> upstream 422 passes (T20, C17) | pass |
| GW-I17 | `PS_APIGATEWAY_DEMO_MODE=false`: `/api/tracking/demo/*` -> 404 for every role including operator; `true`: operator only, buyer/merchant 403 (T9) | pass |
| GW-I18 | `/api/ops/tick`: no/wrong `X-Tick-Secret` -> 401; correct -> system token `sub=svc:poller`, called twice -> idempotent downstream calls; rate limit 30/min IP (value I) | pass |
| GW-I19 | BFF partial: one section stub times out -> 200 with `unavailable` section and `partial:true`; all fail -> 503; no invented data; `mandate_id` shown exactly as checkout reports (S05/S07: `custom_id` survives to capture) | pass |
| GW-I20 | Cold-start sim: upstream stub accepts connection after delay > connect timeout -> 503 `UPSTREAM_WAKING`; GET retried and succeeds; keyed POST retried once; unkeyed money POST not sent (C12, C22) | pass |
| GW-I21 | Mandate/catalog stub down (C14, C15): confirm/capture return 503, never 200; gateway does not cache business data | pass |
| GW-I22 | Audit stub down (C16): reads return 503 `UPSTREAM_UNAVAILABLE`; money path routes unaffected (gateway does not write audit) | pass |
| GW-I23 | Token clock-skew retry: stub returns 401 once for idempotent GET -> re-mint with fresh `iat`, retry once; for unkeyed POST no retry | pass |
| GW-I24 | Key rotation drill: add key B (previous A in JWKS) -> switch signer -> stubs verifying via JWKS accept both during overlap -> retire A -> A-signed tokens rejected | pass |
| GW-I25 | Large/slow upstream response and client disconnect: no resource leak, request still ends with logged status | pass |

## 5. L4 compose / L5 e2e (Playwright) touching the gateway
| ID | Case | Maps to |
|---|---|---|
| GW-E01 | "Start demo" -> demo-session -> `me` shows buyer -> logout | E1, E12 |
| GW-E02 | Session expiry mid-flow -> redirected to start, no data from prior user shown | E12 |
| GW-E03 | Buyer B cannot open buyer A order URL (404/403 page) | E10 |
| GW-E04 | Cold start: edge stopped then started; UI shows "waking server" and recovers on retry without duplicate order | C22, E11 |
| GW-E05 | PayPal return (CI uses the double): static return route with cookie -> capture; return with no cookie -> "sign in again", no auto-capture | T11 |
| GW-E06 | Freeze ON: UI reads `refunds_frozen` and shows queued message; `unknown` treated as frozen | E9 |
| GW-E07 | Honest labels and banned phrases absent on gateway-served pages and error messages ("PayPal-backed", "fraud-proof", "tamper-proof", "legally binding", "production-secure", "zero trust") | T25 |
| GW-E08 | CSP blocks inline script injection attempt (no inline script allowed) | T19/T21 |
Live PayPal approve click and real return URL are manual (G1 spike, task GW-S1-08), recorded in `docs/gates.md`; not CI-gated.

## 6. Security cases (merge-blocking where marked P0)
| ID | Case | Test-strategy ref | P |
|---|---|---|---|
| GW-X01 | Direct call to any service without internal JWT -> 401 (compose, with gateway bypass) | T14 | P1 |
| GW-X02 | JWT matrix at a service stub (missing, expired, wrong aud, alg=none, forged signature, replayed `jti` on money route) | T19 | P0 |
| GW-X03 | Login brute force: per IP+handle limit triggers; error text identical for unknown handle and bad password | T19 | P0 |
| GW-X04 | CSRF: missing token, wrong purpose, other-session token, replayed single-use token, cross-origin POST with cookie but no token | T19 | P0 |
| GW-X05 | CORS preflight from foreign origin: no credentials allowed | T19 | P0 |
| GW-X06 | Header spoofing matrix (GW-I08) incl. `X-Forwarded-For` spoofing against rate limiter | T19, T10 | P0 |
| GW-X07 | Client-supplied money keys rejected / ignored | T22 | P0 |
| GW-X08 | `/internal/*` and unlisted paths -> 404 for every role; unlisted method -> 405 | T19 | P0 |
| GW-X09 | Secret hygiene: gitleaks full history, env-manifest (no `PAYPAL_*`, `LLM_*`, `MANDATE_HMAC_KEY`, `APPROVAL_KEY`), `.env` untracked, image layer grep | T13 | P0 |
| GW-X10 | LLM-route abuse: oversize body 413, 7th call in a minute 429, global budget stop; no LLM key in gateway | T16 | P1 |
| GW-X11 | Error leakage: malformed JSON, huge header, bad unicode, DB down -> uniform body, no traces | T21 | P1 |
| GW-X12 | Log redaction with real traffic including PayPal return query string and approval-token path | T26 | P1 |
| GW-X13 | Supply chain: lockfile present, `pip-audit` clean or waived in `docs/known-issues.md` | T15 | P1 |
| GW-X14 | Approval token path: token never appears in logs, metrics labels, Sentry events (scrubber test) | T26 | P1 |
| GW-X15 | Session fixation and cookie theft via subdomain (`__Host-` prefix prevents Domain attr) | T19 | P0 |
| GW-X16 | Open redirect / SSRF: gateway has no redirect endpoint; upstream `Location` dropped; `approval_url` host-checked | T11, T12 | P1 |

## 7. Chaos subset (L6) relevant to the gateway
C12 (Postgres/Neon cold or refused: session lookup fails closed with 503, no half session), C14, C15, C16, C17, C22 (sleeping consumer), C7-style 429 storm from upstream (no tight retry loop; call count bound). Money-path PRs also run the shared chaos subset (C1-C5, C13, C19, C20) through the gateway in compose.

## 8. Performance / demo-load smoke (honest; no SLA claims)
- k6 or Locust per test-strategy section 12: P1 read smoke (5 VUs x 30 s), P2 three concurrent flows, P3 cold-start probe (record first-request latency after idle, observation only), gateway-added latency p50/p95 measured locally and on the hosted host in week 1 and week 4 (recorded, no target invented). Never load-test live PayPal.

## 9. CI side-by-side commands
Local (Profile A, hermetic: PayPal double, LLM stub) and CI use the same commands; CI adds a Postgres service container. Paths are illustrative until the scaffold lands (I).
| step | local command | CI job (path-filtered: `services/api-gateway/**`, `libs/**`, `contracts/**`) |
|---|---|---|
| lint/types | `uv run ruff check . && uv run ruff format --check .` | same |
| unit | `uv run pytest services/api-gateway/tests/unit -q` | same, fail-fast |
| contract | `uv run python -m app.export_openapi > /tmp/gw.json && diff -u contracts/openapi/api-gateway.json /tmp/gw.json` ; `uv run schemathesis run ...` | same + openapi-diff vs main |
| integration | `docker compose up -d postgres && uv run pytest services/api-gateway/tests/integration -q` | `services: postgres` container, same pytest |
| profile parity | `PS_APIGATEWAY_UPSTREAM_MODE=inprocess uv run pytest services/api-gateway/tests/contract -q` then `=http` | matrix job on both modes |
| env manifest | `uv run pytest services/api-gateway/tests/test_env_manifest.py` | same |
| security | `gitleaks detect --redact` ; `uv run pip-audit` | `gitleaks` full history; `pip-audit` |
| compose system | `docker compose --profile a up -d --wait && uv run pytest tests_system -k gateway` | PR to main + nightly |
| e2e | `pnpm --filter web exec playwright test --grep @gateway` | PR to main + nightly |
| hosted smoke | `scripts/warmup && scripts/smoke --env profile-b` | post-deploy step after health gate; also scheduled every 6 h later (sprint S4-05) |
| live PayPal | not run by gateway suite | separate opt-in `live-paypal.yml` (test-strategy sec 4) |

## 10. Gating per sprint (mirrors test-strategy section 8)
- Week 1 gate: GW-U01-U03, U06-U10, U20-U27, K01, I01-I02, I05-I08, X08-X09 green; deny-by-default token tests; compose boots.
- Week 2 gate: + CSRF/CORS/rate-limit (U13-U19, I03, X04-X07), proxy routes for mandate/catalog/agent/checkout/audit, I09-I13, I15, I20, I23, K03-K08, IDOR (T10) for those routes; JWKS rotation drill I24.
- Week 3 gate: + tracking/resolution routes, I14, I16-I18, E05-E06, X02, X10, tick path; chaos C12, C14-C17, C22.
- Week 4 gate: ALL above, X01, X11-X16, E01-E08, perf smoke recorded, hosted 10-run soak (shared sprint S4-05), final gitleaks full-history.

## 11. Flake and quarantine
Follows test-strategy section 9: no sleeps (fake clock, explicit waits); L1-L4 and L6 have no retries; L5 max one retry, logged. GW-U10, U13-U14, U21-U22, I03, I12, I15, X02-X04, X07 are money-path/trust tests and cannot be quarantined.

## 12. Definition of done (gateway)
- Every route in the route table has a role test (allowed + denied), a 401 test, and a CSRF/Origin test where mutating; unlisted paths 404 (prd metric).
- 0 requests reach a stub with client-supplied identity headers; 0 forbidden env vars; 0 gitleaks findings; 0 OpenAPI drift on main.
- All tokens verify at a service stub; wrong-aud/expired/alg-none rejected.
- Log redaction test green; no stack traces in any error.
- Retry rules proven by call-count assertions; 409 never retried; unkeyed money POST never sent.
- Cold-start behavior measured on the real host in week 1 and week 4, values written in deployment.md (currently unknown), `UPSTREAM_WAKING` UX demonstrated.
- Latency added by gateway recorded (p50/p95, local and hosted); no target invented.
- 3 consecutive golden-path runs hosted on Profile B without manual restart; later 10 consecutive (sprint S4-05).
- Rotation drill done once before submission; honest-claims check (T25) clean for gateway strings.
- No open Sev1/Sev2 in gateway scope (test-strategy section 14); waivers only in `docs/known-issues.md`, none for P0 security tests.

## 13. Open items
- Coverage floors: gateway is not in the money-path floor list but is on the money path as a gate; propose >= 85% lines on `tokens/`, `csrf.py`, `routing/`, `sessions.py` (I) and report, not chase.
- Exact error codes for upstream 409s come from owner services; update GW-I12 when their OpenAPI lands.
- Live return URL, refund PENDING, webhooks remain untested (I); gateway only passes them through.
