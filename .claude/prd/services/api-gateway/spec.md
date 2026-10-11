# api-gateway: technical spec

Labels: V verified, VC vendor claim, I inference/assumption. Stack per ADR-002: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic, httpx, uv workspace. Demo-grade identity; never described as production-secure.

## 1. Position in the system
- `web -> api-gateway -> {mandate, catalog, shopping-agent, checkout, tracking, resolution, audit(read)}` (service-map section 3).
- Not called by services, except JWKS fetch (`GET /.well-known/jwks.json`).
- Never calls: paypal-adapter, triage-ai, any LLM, PayPal. MCP (`/mcp` on paypal-adapter) is not routed (spec 14 C10).
- Sync depth: gateway is level 1; max chain stays 3 (service-map).
- Profile B: runs as process `edge` (hosts/edge.py); upstreams `core`, `ai` reached over HTTPS, or in-process ASGI when co-located.

## 2. Internal modules (services/api-gateway/app/)
| module | responsibility |
|---|---|
| `main.py` | App factory, middleware order, router mounting, OpenAPI export |
| `config.py` | Pydantic Settings, fail-fast on missing/invalid env, forbidden-var check at startup |
| `middleware/request_id.py` | Request id + traceparent (section 8) |
| `middleware/security_headers.py` | CSP, nosniff, Referrer-Policy, frame-ancestors, strip `Server` |
| `middleware/origin_cors.py` | CORS allowlist, Origin/Referer check for mutating methods |
| `middleware/body_limits.py` | Max body, JSON content-type, forbidden-money-key scan |
| `principal.py` | `Principal` dataclass: `actor_type, actor_id, role, session_epoch, auth_method, display_name?`; seam for a future OIDC builder |
| `sessions.py` | Create/lookup/slide/delete sessions, epoch checks, lazy purge of expired rows and ephemeral buyers |
| `auth/passwords.py` | argon2id hash/verify, dummy-hash constant-time path |
| `csrf.py` | CSRF token issue/verify, single-use ledger for sensitive purposes |
| `ratelimit.py` | In-memory sliding/fixed window limiter keyed by session, else IP; global LLM-route counter |
| `routing/table.py` | Declarative route table (section 5): method, path template, upstream, roles, rate class, csrf purpose, idempotency requirement, demo-only flag, forbidden body keys |
| `routing/proxy.py` | Generic proxy handler driven by the table: header allowlist, mint, forward, response filter |
| `tokens/mint.py` | Internal JWT minting (section 7) |
| `tokens/keys.py` | Load current private key from env, public key set from DB metadata + env, JWKS document |
| `upstream.py` | httpx AsyncClient per upstream; `http` or `inprocess` (ASGITransport) mode; timeouts, retry policy, waking detection |
| `bff/` | Read-only aggregators (section 9) |
| `ops.py` | Status, freeze forward, tick |
| `errors.py` | Error model + exception handlers (section 11) |
| `logging.py` | JSON logger, redaction filter, route-template logging |
| `db.py`, `models.py` | SQLAlchemy models for `gateway` schema |
| `health.py` | `/healthz`, `/readyz` |
Rules: no business logic and no imports from other services' app packages; may import `libs/common` (token verify types, logging) and `libs/clients` (typed clients) only.

## 3. Data (schema `gateway`, DB role `gateway_app` with grants only on this schema; Alembic migrations in services/api-gateway/migrations)
| table | key columns | notes |
|---|---|---|
| `users` | `id uuid pk`, `handle unique`, `role` (buyer\|merchant\|operator), `actor_type`, `display_name`, `password_hash null`, `is_ephemeral bool`, `epoch int`, `created_at`, `disabled_at null` | 2-3 seeded rows (buyer persona optional, merchant, operator) + ephemeral buyers from "Start demo". Hashes are made by seed script from env-provided passwords; no passwords or hashes committed |
| `sessions` | `sid_hash pk` (SHA-256 of cookie value), `user_id fk`, `role`, `epoch`, `created_at`, `last_seen_at`, `expires_at`, `ip_hash`, `ua_hash` | Raw sid never stored or logged. `ip_hash` salted (salt from `PS_APIGATEWAY_CSRF_KEY`-derived, I) |
| `csrf_uses` | `jti pk`, `sid_hash`, `purpose`, `expires_at` | Single-use ledger for sensitive purposes; purged lazily |
| `signing_keys` | `kid pk`, `alg`, `public_key_pem`, `status` (current\|previous\|retired), `created_at`, `retire_after` | Metadata and public keys only; private key stays in env |
| `settings` | `key pk`, `value` | `global_epoch`; nothing else |
No outbox (gateway emits no events). Pool kept small (Neon free, shared connection budget: I).

## 4. Session model
### 4.1 Cookie and row
- Name `__Host-ps_sid` (requires Secure, Path=/, no Domain). Value: 256-bit random, base64url. Attributes: HttpOnly, Secure, SameSite=Lax.
- Lookup: SHA-256(cookie) -> row; invalid if missing, expired, `row.epoch != users.epoch`, `users.epoch`-bumped, or `row.epoch < settings.global_epoch`, or user disabled. All -> 401 `UNAUTHENTICATED` and an expired-cookie `Set-Cookie`.
- Sliding expiry up to a hard cap (starting values I: buyer sliding 2 h / cap 8 h; merchant and operator 1 h). Slide writes are throttled (update `last_seen_at` at most once per minute per session) to spare the DB.
- Login always issues a NEW sid; any presented old sid is deleted (fixation).
### 4.2 Actors
| actor_type | creation | role | notes |
|---|---|---|---|
| `buyer` | `POST /api/auth/demo-session` (ephemeral) or seeded persona login | buyer | Ephemeral buyers get a random handle; cap on live ephemeral buyers (config) to stop table abuse |
| `merchant_shared` | password login | merchant | DISCLOSED single shared login |
| `operator` | password login | operator | Demo clock, force late/lost, freeze/unfreeze. Separate credentials from merchant |
### 4.3 Topology (decide week 1, test with real PayPal return)
- Preferred: Vercel `rewrites` map `/api/*` and `/.well-known/jwks.json` (optional) to the gateway origin so the browser sees one site; cookies are first-party and SameSite=Lax works. Vercel proxied timeout 120 s (V) caps gateway total time per request.
- Fallback: custom subdomains of one registrable domain (domain costs money: only if free option found, I).
- If neither works: separate domains break Lax cookies (I). Then the web app would need a different session mechanism; treated as risk R3, not designed here.
- PayPal return: PayPal redirects the browser to a static web route (Vercel) carrying `token`, `PayerID`, `state`; that route calls `POST /api/checkout/orders/{id}/capture` with the cookie. If the cookie is missing, show "sign in again" and never auto-capture (auth-gateway section 5).

## 5. Route table (public surface; default deny)
Role codes: A anon, B buyer, M merchant, O operator. "CSRF" = CSRF token required (plus Origin check on all mutating methods); "S" = single-use fresh token. "Idem" = `Idempotency-Key` required. RL = rate-limit class (section 6). Owner service enforces ownership via `act.actor_id`.

### 5.1 Gateway-owned
| method | path | roles | CSRF | RL | notes |
|---|---|---|---|---|---|
| GET | `/healthz` | A | - | health | no DB |
| GET | `/readyz` | A | - | health | DB + key loaded; `?deep=true` also pings upstream `/healthz` (warm-up only, operator or tick secret required) |
| GET | `/.well-known/jwks.json` | A | - | read-anon | public keys only; cacheable |
| POST | `/api/auth/demo-session` | A | Origin only | auth | creates ephemeral buyer + session |
| POST | `/api/auth/login` | A | Origin only | auth-login | body handle+password |
| POST | `/api/auth/logout` | B,M,O | CSRF | write | deletes session |
| GET | `/api/auth/me` | B,M,O | - | read | Principal |
| GET | `/api/auth/csrf?purpose=` | B,M,O | - | read | returns token; `purpose` in an enum |
| GET | `/api/ops/status` | B,M,O | - | read | freeze flag (read via owner), demo mode, build id |
| POST | `/api/ops/freeze` | O | CSRF+S | write | forwards to flag owner (C6) |
| POST | `/api/ops/tick` | A with `X-Tick-Secret` | secret instead of CSRF | tick | system token `svc:poller` |
| GET | `/api/bff/buyer-home`, `/api/bff/orders/{id}`, `/api/bff/merchant-queue` | B (first two), M,O (third) | - | read | section 9 |

### 5.2 Proxied (path = `/api/<svc>` + upstream path)
| method | public path | upstream | roles | CSRF | Idem | RL | notes |
|---|---|---|---|---|---|---|---|
| POST | `/api/mandate/mandates` | mandate `POST /mandates` | B | CSRF+S (`mandate_sign`) | yes | sensitive | upstream also consumes its own nonce (C4) |
| GET | `/api/mandate/mandates/{id}` | `GET /mandates/{id}` | B,M,O | - | - | read | merchant sees upstream-defined summary |
| GET | `/api/mandate/mandates/{id}/terms` | `GET /mandates/{id}/terms` | B,M,O | - | - | read | |
| POST | `/api/mandate/mandates/{id}/revoke` | `POST /mandates/{id}/revoke` | B | CSRF+S (`mandate_revoke`) | optional | sensitive | idempotent upstream |
| GET | `/api/catalog/items`, `/api/catalog/items/{id}` | catalog | B,M,O | - | - | read | |
| POST | `/api/agent/propose` | shopping-agent `POST /propose` | B | CSRF | yes | llm | LLM budget counter; strict body size |
| POST | `/api/checkout/carts` | checkout `POST /carts` | B | CSRF | yes | write | forbidden money keys |
| POST | `/api/checkout/carts/{id}/confirm` | `POST /carts/{id}/confirm` | B | CSRF+S (`order_confirm`) | yes | sensitive | money route |
| POST | `/api/checkout/orders/{id}/capture` | `POST /orders/{id}/capture` | B | CSRF | yes | sensitive | money route; body carries `state`, `token`, `PayerID` as opaque strings |
| GET | `/api/checkout/orders/{id}` , `/api/checkout/orders?mandate_id=` | checkout | B,M,O | - | - | read | |
| POST | `/api/tracking/shipments` | tracking `POST /shipments` | M | CSRF | yes | write | |
| GET | `/api/tracking/shipments/{order_id}` | tracking | B,M,O | - | - | read | label SIMULATED CARRIER in payload (upstream) |
| POST | `/api/tracking/demo/clock/advance` | tracking | O | CSRF | - | write | `PS_APIGATEWAY_DEMO_MODE` only |
| POST | `/api/tracking/demo/shipments/{id}/force` | tracking | O | CSRF | - | write | `PS_APIGATEWAY_DEMO_MODE` only |
| POST | `/api/resolution/cases/report` | resolution `POST /cases/report` | B | CSRF | yes | llm | free text untrusted; length cap |
| GET | `/api/resolution/cases/{id}`, `/api/resolution/cases?status=` | resolution | B (own, upstream enforces), M, O | - | - | read | list is M/O only |
| POST | `/api/resolution/offers/{id}/accept` | `POST /offers/{id}/accept` | B | CSRF+S (`offer_accept`) | yes | sensitive | money route |
| POST | `/api/resolution/approvals/{token}/consent` | `POST /approvals/{token}/consent` | B | CSRF+S (`approval_consent`) | yes | sensitive | money route; token in path: never logged (log template) |
| POST | `/api/resolution/cases/{id}/merchant-action` | resolution | M | CSRF | yes | write | creates NEW offer upstream |
| GET | `/api/audit/entries`, `/api/audit/verify` | audit | B,M,O | - | - | read | public-safe fields are upstream's job |
Not exposed: `/mandates/{id}/evaluate`, `/prices/resolve`, `/intent-fit`, `/detector/run`, `/refunds/reconcile`, `/append`, `/internal/*`, paypal-adapter, triage-ai, MCP.
Tracker status mutation does not exist: PayPal accepts PATCH only to CANCELLED (V), and carrier state is ours, so no route offers it.

## 6. CSRF, CORS, rate limits
### 6.1 CSRF
- Layers: SameSite=Lax; Origin (else Referer) host must be in `PS_APIGATEWAY_FRONTEND_ORIGINS` on POST/PUT/PATCH/DELETE; `X-CSRF-Token`.
- Token = `v1.<purpose>.<ts>.<jti>.<mac>`, `mac = HMAC-SHA256(PS_APIGATEWAY_CSRF_KEY, sid_hash || purpose || ts || jti)`. Verified constant-time, TTL config (starting value I: 10 min for general, 120 s for single-use purposes to match the mandate challenge window in auth-gateway section 4.1).
- Single-use purposes insert `jti` into `csrf_uses` atomically (unique violation -> 403 `CSRF_REPLAYED`).
- General purpose `general` may be reused until expiry. Login and demo-session are Origin-checked only (no session exists yet).
- Note: auth-gateway text uses a per-session csrf secret; this spec derives from `PS_APIGATEWAY_CSRF_KEY` + `sid_hash` to avoid storing a per-session secret (minor deviation, same security property for demo; C5).
### 6.2 CORS
- Allowed origins: exact list from env. `Allow-Credentials: true` only for an exact origin match. Methods and headers allowlisted (`Content-Type`, `X-CSRF-Token`, `Idempotency-Key`, `X-Request-Id`). No wildcard; preflight cache config. `/internal/*` never exists.
- With the Vercel rewrite the browser makes same-origin calls; CORS stays enabled for the explicit origin(s) as a fallback (local dev at localhost).
### 6.3 Rate limits (starting values I from auth-gateway 2.4; tune after load test)
| class | limit | key |
|---|---|---|
| auth (demo-session) | 10/min | IP |
| auth-login | stricter than auth (value decided in implementation; I) | IP + handle |
| llm | 6/min | session; plus global daily counter, hard stop -> 429 `LLM_BUDGET_EXHAUSTED` |
| sensitive | 5/min | session |
| write | value decided in implementation (I) | session |
| read | 120/min | session |
| tick | 30/min | IP |
| health | generous, separate | IP |
- Exceeded -> 429 `RATE_LIMITED` + `Retry-After`; counted in logs and metric (not audited: gateway emits no events, C7).
- Limiter is per process, in memory; resets on restart or sleep. Behind a proxy, client IP is taken from the platform's forwarded header only for the configured number of trusted hops (`TRUSTED_PROXY_COUNT`), otherwise ignored.

## 7. Internal JWT minting
- Library: PyJWT with `cryptography` (EdDSA/Ed25519). Alg pinned in verifier config; `none` and alg switching rejected (verifier side, tested via contract fixtures).
- Header: `alg=EdDSA`, `kid`. Claims:
  - `iss` = `api-gateway`; `sub` = user id (or `svc:poller` for tick); `aud` = exactly one target service slug; `iat`, `exp` (default 60 s; hard max 120 s per ADR-006); `jti` uuid4; `req` = request id.
  - `act` = `{actor_type, actor_id, role, auth_method, display_name?}` where `auth_method` is `session+csrf`, `session+csrf+nonce`, `session+approval_token` (consent route), `tick_secret`, or `none` (read-only GET).
  - `role` also at top level (ADR-006 / service-map: `sub`, `role`, `jti`, optional `mandate_id`).
  - `mandate_id` only when the path contains one; advisory routing hint, receiving service must still verify ownership.
  - `sid` = `sid_hash` (hash only) so checkout can bind PayPal return `state` to the session (C8).
  - `scope` = list derived from the route table (e.g. `mandate:sign`, `checkout:capture`); services must check scope AND role.
- One token per upstream call. Never reused across `aud`. Never logged. Never returned to the browser.
- Keys: current Ed25519 private key in env (`PS_APIGATEWAY_SIGNING_KEY_PEM`, `PS_APIGATEWAY_SIGNING_KID`); public keys of current + previous in `signing_keys`/env; JWKS exposes both. Verifiers fetch and cache JWKS and may fall back to a static `trusted_issuers` env (cold-start resilience, C1).
- Rotation: add new public key -> deploy -> switch signer -> keep previous for max TTL + overlap -> retire. A rotation drill is planned before submission (auth-gateway 3.4).
- Retry rule: on upstream 401 caused by clock skew, mint again once with fresh `iat` and retry (idempotent calls only). Skew tolerance at verifier is <= 5 s (auth-gateway 3.1).

## 8. Header stripping, request ids, trace ids
- Request headers forwarded (allowlist): `Content-Type`, `Accept`, `Idempotency-Key`, `If-Match`/`If-None-Match` (if used upstream), plus gateway-injected `Authorization: Bearer <internal jwt>`, `X-Request-Id`, `traceparent`. Everything else dropped, in particular `Cookie`, any inbound `Authorization`, and the families `X-User-*`, `X-Actor-*`, `X-Role*`, `X-Auth-*`, `X-Internal-*`, `X-Forwarded-*`, `Forwarded`, `X-Real-IP`.
- Inbound `X-Request-Id` is ignored; a new uuid4 is generated and echoed. Inbound `traceparent` accepted only if it matches the W3C format (version 00, 32-hex trace id not all zero, 16-hex parent id); otherwise a new trace is started. Gateway creates its own span id for the upstream call.
- Response headers forwarded (allowlist): `Content-Type`, `Cache-Control` (default `no-store` for authenticated data), `Retry-After`, `ETag`. Upstream `Set-Cookie`, `Server`, `Location` dropped (no redirects through the gateway; PayPal approval URL comes in JSON and is host-checked, REQ-GW-037).
- Log fields: `request_id, trace_id, route_template, method, status, latency_ms, upstream, principal_hash`. `route_template` is used instead of the raw path so `approvals/{token}` never reaches logs; query strings are never logged (PayPal `token`/`PayerID`/`state`).

## 9. BFF aggregation (read-only)
- Endpoints: `buyer-home` (mandates summary, latest order, active case), `orders/{id}` (order + shipment + case + audit verify flag), `merchant-queue` (cases by status + tracking pending).
- Each section is fetched in parallel with its own timeout; failures return `"sections": {"x": {"status":"unavailable"}}` plus HTTP 200 (partial), never invent data. A fully failed BFF returns 503.
- Requires list endpoints that are not in service-map today: mandate list by buyer, checkout orders by buyer (C9). If not added, BFF `buyer-home` is cut and the UI uses direct proxied reads.
- Contains no joins on money fields; passes upstream values through unchanged (shows PayPal `custom_id`-derived `mandate_id` exactly as checkout reports it, V: survives to capture).

## 10. Freeze flag handling
- Concept (threat-model section 10): global `REFUNDS_FROZEN`, default fail-closed, read by resolution, paypal-adapter and MCP at three points. "Stop wins": freeze beats approvals, in-flight APPROVED items, retries and the poller.
- Gateway role:
  - Never decides refund eligibility, never short-circuits in a way that loses queued work.
  - `GET /api/ops/status` shows `frozen: true|false|unknown` from the flag owner (unknown if unreachable; UI treats unknown as frozen, i.e. shows the safer message).
  - `POST /api/ops/freeze {frozen, reason}` is operator-only, requires single-use CSRF, forwards to the owner with an operator token; the owner writes an audit entry (actor stamped from the token).
  - Unfreeze requires operator role and a non-empty reason (owner validates).
  - Merchant role cannot toggle.
- Separate gateway-local switch `PS_APIGATEWAY_MONEY_ROUTES_ENABLED` (env): when false, money-mutating routes (confirm, capture, offer accept, consent) return 503 `MONEY_ROUTES_DISABLED`. This is a UI-edge brake, not a substitute for the owner-enforced freeze, and is read at request time (restart or env change needed on free hosts: I).
- Which service owns the flag row is undecided (C6).

## 11. Error model
- Body: `{"error": "<CODE>", "message": "<human text, no internals>", "request_id": "<uuid>", "details": {optional}}`. `Retry-After` header where relevant.
- Gateway codes: `UNAUTHENTICATED` 401, `FORBIDDEN` 403, `CSRF_FAILED` 403, `CSRF_REPLAYED` 403, `ORIGIN_NOT_ALLOWED` 403, `NOT_FOUND` 404, `METHOD_NOT_ALLOWED` 405, `PAYLOAD_TOO_LARGE` 413, `UNSUPPORTED_MEDIA_TYPE` 415, `VALIDATION_FAILED` 422, `CLIENT_MONEY_FIELD_REJECTED` 422, `IDEMPOTENCY_KEY_REQUIRED` 400, `RATE_LIMITED` 429, `LLM_BUDGET_EXHAUSTED` 429, `MONEY_ROUTES_DISABLED` 503, `UPSTREAM_WAKING` 503, `UPSTREAM_UNAVAILABLE` 503, `UPSTREAM_TIMEOUT` 504, `UPSTREAM_BAD_RESPONSE` 502, `INTERNAL` 500.
- Upstream errors: JSON error bodies from services (same model) pass through with status unchanged and `request_id` replaced by the gateway's; non-JSON or malformed bodies become `UPSTREAM_BAD_RESPONSE`. Upstream 409 is passed through (not retried); upstream 422 such as PayPal `REFUND_AMOUNT_EXCEEDED` or `DUPLICATE_INVOICE_ID` (V) reaches the UI as the owning service's mapped code, never raw PayPal text.
- Auth errors do not reveal whether a handle exists. Stack traces never returned.

## 12. Honest-claims constraints (apply to code strings, README, UI copy, video)
May say:
- "Gateway-owned demo sessions; services verify short-lived audience-bound tokens; client identity headers are stripped."
- "PayPal credentials live in one service; the gateway has none."
- "Merchant login is one shared demo login; operator is a separate demo login."
Must NOT say: PayPal-backed/verified/protected; production-secure; zero trust; compliant; non-repudiable; legally binding; injection-proof; fraud-proof; tamper-proof; real carrier data; real money; individual merchant accountability; measured SLA.
Also: CSRF/CORS/rate limits are "demo-grade controls"; rate limiter is single-instance in-memory.

## 13. Config and environment variables (names only; values live in platform env)
| name | purpose | secret? |
|---|---|---|
| `PS_APIGATEWAY_APP_ENV` | local/ci/staging/demo | no |
| `PS_APIGATEWAY_DEMO_MODE` | enable `/api/tracking/demo/*` routes | no |
| `PORT` | listen port (platform-injected) | no |
| `PS_APIGATEWAY_LOG_LEVEL` | log verbosity | no |
| `PS_APIGATEWAY_DATABASE_URL` | Postgres pooled URL, `gateway_app` role | yes |
| `PS_APIGATEWAY_FRONTEND_ORIGINS` | comma list of exact web origins | no |
| `PS_APIGATEWAY_COOKIE_NAME` | default `__Host-ps_sid` | no |
| `PS_APIGATEWAY_SESSION_TTL_BUYER_S`, `PS_APIGATEWAY_SESSION_CAP_BUYER_S`, `PS_APIGATEWAY_SESSION_TTL_STAFF_S` | session lifetimes | no |
| `PS_APIGATEWAY_MAX_EPHEMERAL_BUYERS` | cap for demo-session | no |
| `PS_APIGATEWAY_CSRF_KEY` | CSRF HMAC + salt derivation | yes |
| `PS_APIGATEWAY_SESSION_COOKIE_KEY` | reserved for cookie-value signing if adopted (auth-gateway lists it); unused if cookie is purely opaque | yes |
| `PS_APIGATEWAY_SIGNING_KEY_PEM`, `PS_APIGATEWAY_SIGNING_KID` | current Ed25519 key | yes |
| `PS_APIGATEWAY_PREVIOUS_PUBLIC_KEYS` | JSON list of previous public keys for JWKS overlap | no |
| `PS_APIGATEWAY_INTERNAL_TOKEN_TTL_S` | default 60, max 120 | no |
| `PS_APIGATEWAY_UPSTREAM_MODE` | `http` or `inprocess` | no |
| `PS_APIGATEWAY_UPSTREAM_MANDATE_URL`, `PS_APIGATEWAY_UPSTREAM_CATALOG_URL`, `PS_APIGATEWAY_UPSTREAM_SHOPPING_AGENT_URL`, `PS_APIGATEWAY_UPSTREAM_CHECKOUT_URL`, `PS_APIGATEWAY_UPSTREAM_TRACKING_URL`, `PS_APIGATEWAY_UPSTREAM_RESOLUTION_URL`, `PS_APIGATEWAY_UPSTREAM_AUDIT_URL` | base URLs (Profile A/B) | no |
| `PS_APIGATEWAY_UPSTREAM_CONNECT_TIMEOUT_S`, `PS_APIGATEWAY_UPSTREAM_READ_TIMEOUT_S`, `PS_APIGATEWAY_UPSTREAM_TOTAL_BUDGET_S`, `PS_APIGATEWAY_UPSTREAM_RETRIES` | timeouts and retry (values chosen after week-1 measurement; total budget must stay under the web host proxy limit) | no |
| `PS_APIGATEWAY_MAX_BODY_BYTES` | body cap | no |
| `PS_APIGATEWAY_RATE_LIMIT_*` | per-class overrides | no |
| `PS_APIGATEWAY_LLM_DAILY_BUDGET_CALLS` | gateway-side global counter for llm class (not an LLM key) | no |
| `PS_APIGATEWAY_MONEY_ROUTES_ENABLED` | gateway brake | no |
| `PS_APIGATEWAY_TICK_SECRET` | `/api/ops/tick` header secret | yes |
| `PS_APIGATEWAY_TRUSTED_PROXY_COUNT` | forwarded-IP hops | no |
| `PS_APIGATEWAY_APPROVAL_URL_HOST_ALLOWLIST` | hosts allowed in checkout `approval_url` (exact sandbox host to confirm: I) | no |
| `SEED_MERCHANT_PASSWORD`, `SEED_OPERATOR_PASSWORD`, `SEED_BUYER_PASSWORD` | read ONLY by `scripts/seed`, not by the running app | yes |
| `PS_APIGATEWAY_SENTRY_DSN` | optional error tracking | yes |
Forbidden in this service (CI env-manifest test): `PAYPAL_*`, `LLM_API_KEY`/`LLM_PROVIDER` keys, `MANDATE_HMAC_KEY`, `APPROVAL_KEY`.

## 14. Open questions / conflicts (decisions taken here; other agents' files untouched)
| id | conflict or gap | sources | decision in this spec |
|---|---|---|---|
| C1 | JWKS: ADR-006/service-map say verifiers use cached JWKS and gateway exposes JWKS; auth-gateway 3.1 says static `trusted_issuers`, no runtime JWKS fetch (cold starts) | adr, service-map vs auth-gateway | Follow ADR: expose JWKS; recommend verifiers also accept a static env fallback. Needs confirmation from the libs/common owner |
| C2 | Internal token TTL: ADR-006 60-120 s; auth-gateway <= 60 s | adr vs auth-gateway | Default 60 s, hard max 120 s |
| C3 | Roles: service-map says buyer\|merchant; auth-gateway/threat-model add reviewer and a separate operator/demo-admin | service-map vs others | Roles = buyer, merchant, operator. Reviewer folded into merchant (service-map puts case queue and brief in merchant UI). Operator added because threat-model T9/T20 require freeze and clock separate from the shared merchant login. Service-map should list operator |
| C4 | Nonce ownership: auth-gateway has gateway issue the mandate-sign nonce; service-map/overview F1 give nonces to mandate | auth-gateway vs service-map | Mandate owns its nonce (service-map). Gateway issues only CSRF tokens (single-use for sensitive purposes) |
| C5 | CSRF construction: per-session `csrf_secret_hash` vs derived HMAC | auth-gateway | Derived from `PS_APIGATEWAY_CSRF_KEY` + `sid_hash`; no per-session secret |
| C6 | Freeze flag owner not named in service-map (threat-model: Postgres row read by resolution + adapter + MCP; auth-gateway: env `PS_PAYPALADAPTER_MONEY_ENABLED` read by adapter) | threat-model vs auth-gateway vs service-map | Gateway forwards toggle to "the owner"; recommendation: resolution owns the row and exposes it to the adapter, or the adapter owns it; needs a decision by the resolution/paypal-adapter authors. Gateway reads status only |
| C7 | Audit of auth events (`rate_limited`, login, csrf fail): auth-gateway wants audit; service-map says gateway emits no events and has no outbox | auth-gateway vs service-map | No events (service-map); structured logs and counters only. If wanted: add `gateway.security_event` + outbox (extra scope, P2) |
| C8 | PayPal return `state` binding: auth-gateway puts `return_bindings` in the gateway; service-map says gateway owns no business data and checkout owns orders/capture | auth-gateway vs service-map | Checkout owns the binding; gateway forwards `sid` (hash) claim so checkout can verify the session match |
| C9 | Missing list endpoints for the BFF (mandates by buyer, orders by buyer, mandate list) | service-map | Request additions to mandate/checkout; otherwise BFF `buyer-home` is cut |
| C10 | MCP external exposure for the Agentic Commerce demo | threat-model Q | Not routed by gateway in v1. If exposed, it needs its own scoped demo token and a read/propose-only tool subset; decision pending |
| C11 | Profile naming: overview/service-map call A = every service separate, B = co-located; deployment-zero-cost calls (a) demo-hardened and (b) separate | overview vs deployment-zero-cost | Follow overview: A separate, B co-located |
| C12 | Health paths: overview `/healthz` `/readyz`; deployment-zero-cost `/health`, `/health/deep` | overview vs deployment-zero-cost | `/healthz`, `/readyz`; deep via `/readyz?deep=true` (restricted). Pinger must use `/healthz` (V math: 24/7 DB pings exhaust Neon CU-h) |
| C13 | Render 750 h/month per workspace (V) vs overview Profile B with 4 backend processes plus keep-alive | deployment-zero-cost vs overview | Cannot keep 4 processes 24/7. See deployment.md section 2: only `edge` pinged 24/7 at most; others warmed in windows; fallback is a single-process host mounting all apps |
| C14 | Ephemeral per-visitor buyer (auth-gateway) vs seeded accounts (ADR/service-map) | auth-gateway vs adr | Both: seeded accounts (merchant, operator, optional buyer persona) plus ephemeral buyers created by Start demo |
| C15 | Revoke semantics for already-captured orders | 00-platform-prd.md D1, user-confirmed 2026-10-10: revoke stops future carts/spend only; protection already earned on captured orders stands. No gateway impact; UI copy owned by web. |
| C16 | `approval_url` host for PayPal sandbox (exact host not recorded in the brief) | brief | Configurable allowlist, confirm in week 1 spike (I) |
| C17 | Numbers in rate limits, TTLs are starting values (I) | auth-gateway | Tune after load test; no claim made |
