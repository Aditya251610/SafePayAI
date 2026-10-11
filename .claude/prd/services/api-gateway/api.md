# api-gateway: API reference

Labels: V verified, VC vendor claim, I inference/assumption. Source of truth: spec.md (sections 5, 6, 7, 11), prd.md. Contract file: `contracts/openapi/api-gateway.json` (committed, CI drift check, ADR-008). Examples below are illustrative; ids are placeholders, no secrets.

## 1. Conventions (all endpoints)
- Base: browser calls `/api/...` on the web origin; Vercel rewrite forwards to the gateway (spec 4.3, decide week 1: I). `/healthz`, `/readyz`, `/.well-known/jwks.json` are root paths.
- Auth: cookie `__Host-ps_sid` (HttpOnly, Secure, SameSite=Lax). No bearer from browsers. Roles: A anon, B buyer, M merchant, O operator.
- Mutating methods (POST/PUT/PATCH/DELETE): allowlisted `Origin` (else `Referer`) AND `X-CSRF-Token` (except demo-session, login, tick). Sensitive purposes need a fresh single-use token (replay -> 403 `CSRF_REPLAYED`).
- Request headers: `Content-Type: application/json` on mutating routes; `Idempotency-Key` (client uuid) where "Idem: required"; optional `traceparent` (accepted only if well-formed). Inbound `X-Request-Id` is ignored.
- Response headers on every response (incl. errors): `X-Request-Id`, security headers, `Cache-Control: no-store` for authenticated data.
- Money: integer minor units only; currency is server-derived. Routes that take ids/quantities only reject `amount`, `currency`, `merchant`, `capture_id`, `price`, `total` with 422 `CLIENT_MONEY_FIELD_REJECTED`.
- Error body (all errors): `{"error":"CODE","message":"text","request_id":"<uuid>","details":{...optional}}`.
- Events: the gateway emits and consumes none (service-map). Where a route triggers an upstream event, it is listed as "upstream event".
- Gateway never forwards `Cookie`, inbound `Authorization`, `X-User-*`, `X-Actor-*`, `X-Role*`, `X-Auth-*`, `X-Internal-*`, `X-Forwarded-*`. It mints one EdDSA internal JWT per upstream call (aud = one service, exp default 60 s, max 120 s).

## 2. Error codes (gateway)
| code | status | when |
|---|---|---|
| `UNAUTHENTICATED` | 401 | no/invalid/expired session, epoch mismatch, disabled user (also clears cookie) |
| `FORBIDDEN` | 403 | role not allowed on route |
| `CSRF_FAILED` | 403 | missing/invalid/expired `X-CSRF-Token` or wrong purpose |
| `CSRF_REPLAYED` | 403 | single-use token reused |
| `ORIGIN_NOT_ALLOWED` | 403 | Origin/Referer not in `PS_APIGATEWAY_FRONTEND_ORIGINS` |
| `NOT_FOUND` | 404 | unknown path; `/internal/*` always |
| `METHOD_NOT_ALLOWED` | 405 | known path, wrong method |
| `PAYLOAD_TOO_LARGE` | 413 | body over cap |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | not JSON on mutating route |
| `VALIDATION_FAILED` | 422 | schema failure |
| `CLIENT_MONEY_FIELD_REJECTED` | 422 | forbidden money key in body |
| `IDEMPOTENCY_KEY_REQUIRED` | 400 | money-affecting POST without `Idempotency-Key` |
| `RATE_LIMITED` | 429 | class limit hit; `Retry-After` set |
| `LLM_BUDGET_EXHAUSTED` | 429 | global LLM-route counter hard stop |
| `MONEY_ROUTES_DISABLED` | 503 | `PS_APIGATEWAY_MONEY_ROUTES_ENABLED=false` on confirm/capture/accept/consent |
| `UPSTREAM_WAKING` | 503 | connect timeout (likely sleeping free host); `Retry-After` |
| `UPSTREAM_UNAVAILABLE` | 503 | upstream refused/5xx after allowed retries |
| `UPSTREAM_TIMEOUT` | 504 | total budget exceeded |
| `UPSTREAM_BAD_RESPONSE` | 502 | non-JSON/malformed upstream body |
| `INTERNAL` | 500 | unexpected; no internals leaked |
Upstream JSON errors pass through with status unchanged and the gateway's `request_id`. Upstream 409 on capture/refund-class calls is passed through as "in progress" and never retried (V: PayPal concurrent same-Request-Id gives 409). PayPal 422s (`REFUND_AMOUNT_EXCEEDED`, `DUPLICATE_INVOICE_ID`, V) reach the UI only as the owning service's mapped code.

## 3. Gateway-owned endpoints

### GET /healthz  (A)
- Liveness, no DB. 200 `{"status":"ok"}`. Rate class: health. Pinger target.

### GET /readyz  (A; `?deep=true` needs operator session or `X-Tick-Secret`)
- Checks DB reachable + signing key loaded. `deep=true` also calls each upstream `/healthz` (warm-up only).
```json
200 {"status":"ready","db":"ok","signing_key":"loaded"}
200 (deep) {"status":"ready","upstreams":{"core":"ok","ai":"waking","paypal":"ok"}}
503 {"error":"UPSTREAM_UNAVAILABLE","message":"Database not reachable","request_id":"..."}
```

### GET /.well-known/jwks.json  (A)
- Public keys only (current + previous). Cacheable. Verifiers may also keep a static fallback (spec C1).
```json
200 {"keys":[{"kty":"OKP","crv":"Ed25519","kid":"<kid>","alg":"EdDSA","use":"sig","x":"<base64url>"}]}
```

### POST /api/auth/demo-session  (A; Origin check only; RL auth)
- Creates an ephemeral buyer and a session. No PII. Sets cookie. New sid every time.
```json
Request: {}
201 {"principal":{"actor_type":"buyer","actor_id":"<uuid>","role":"buyer","display_name":"demo-buyer-xxxx"},"expires_at":"<iso8601>"}
429 {"error":"RATE_LIMITED",...}   (+ Retry-After)
503 {"error":"UPSTREAM_UNAVAILABLE",...}   (ephemeral buyer cap MAX_EPHEMERAL_BUYERS reached or DB down)
```

### POST /api/auth/login  (A; Origin check only; RL auth-login, key IP+handle)
- Seeded merchant/operator (optional buyer persona). argon2id verify; constant-time path for unknown handle; same error for unknown handle and bad password.
```json
Request: {"handle":"merchant","password":"<entered by user>"}
200 {"principal":{"actor_type":"merchant_shared","actor_id":"<uuid>","role":"merchant","display_name":"Shared merchant (demo)"},"expires_at":"<iso8601>"}
401 {"error":"UNAUTHENTICATED","message":"Invalid credentials","request_id":"..."}
429 {"error":"RATE_LIMITED",...}
```
- Idempotency: not applicable (each login issues a new sid; presented old sid is deleted).

### POST /api/auth/logout  (B,M,O; CSRF general)
- Deletes the session row, expires the cookie. 204. Repeat with dead session -> 401.

### GET /api/auth/me  (B,M,O)
```json
200 {"actor_type":"buyer","actor_id":"<uuid>","role":"buyer","auth_method":"session","display_name":"demo-buyer-xxxx","session_expires_at":"<iso8601>"}
401 {"error":"UNAUTHENTICATED",...}
```

### GET /api/auth/csrf?purpose=  (B,M,O)
- `purpose` enum: `general`, `mandate_sign`, `approval_consent`, `mandate_revoke`, `offer_accept`, `order_confirm`, `ops_freeze`. Token format `v1.<purpose>.<ts>.<jti>.<mac>`; TTL config (starting I: 10 min general, 120 s single-use).
```json
200 {"csrf_token":"v1.mandate_sign.<ts>.<jti>.<mac>","purpose":"mandate_sign","expires_at":"<iso8601>"}
422 {"error":"VALIDATION_FAILED","message":"Unknown purpose",...}
```
- Header `X-CSRF-Token` is then sent on the mutating call. Single-use purposes are recorded in `csrf_uses`.

### GET /api/ops/status  (B,M,O)
```json
200 {"demo_mode":true,"money_routes_enabled":true,"refunds_frozen":"false","build_id":"<git sha>"}
```
- `refunds_frozen` is `"true"|"false"|"unknown"`; unknown (owner unreachable) must be shown as frozen by the UI (spec 10). Owner of the flag is open (spec C6).

### POST /api/ops/freeze  (O; CSRF + single-use `ops_freeze`)
- Forwards to the flag owner with an operator token; the owner validates and audits. Merchant gets 403.
```json
Request: {"frozen":false,"reason":"Rehearsal take 2"}
200 {"refunds_frozen":"false","changed_at":"<iso8601>"}
403 {"error":"FORBIDDEN",...}
422 {"error":"VALIDATION_FAILED","message":"Reason required to unfreeze",...}
503 {"error":"UPSTREAM_UNAVAILABLE",...}
```
- Idempotent by value (setting the same state again is a no-op upstream). Upstream event: owner audit entry (not emitted by gateway).

### POST /api/ops/tick  (A with `X-Tick-Secret`; RL tick)
- Cron use. Mints `sub=svc:poller` token, triggers tracking detector and resolution reconcile.
```json
Request: {}
202 {"detector":"accepted","reconcile":"accepted"}
401 {"error":"UNAUTHENTICATED",...}   (missing/wrong secret)
503 {"error":"UPSTREAM_WAKING","message":"Server is waking, retry","request_id":"..."}  (+ Retry-After)
```
- Idempotent: downstream `/detector/run` and `/refunds/reconcile` are idempotent (service-map). Upstream events: tracking `shipment.late_detected` / `lost_detected`, resolution `case.*` / `refund.*`.

### GET /api/bff/buyer-home  (B)   [P1; cut if C9 list endpoints missing]
### GET /api/bff/orders/{id}  (B)
### GET /api/bff/merchant-queue  (M,O)
- Read-only fan-out in parallel, per-section timeout. Partial results return 200 with unavailable sections; all sections failed -> 503. Values are passed through unchanged (money fields not recomputed).
```json
200 {"sections":{
  "order":{"status":"ok","data":{"id":"<order uuid>","mandate_id":"<uuid>","state":"CAPTURED"}},
  "shipment":{"status":"ok","data":{"label":"SIMULATED CARRIER","state":"..."}},
  "case":{"status":"unavailable"},
  "audit":{"status":"ok","data":{"chain_ok":true}}
 },"partial":true}
404 {"error":"NOT_FOUND",...}      (owning service says not yours or missing; no existence leak)
503 {"error":"UPSTREAM_UNAVAILABLE",...}
```
- Inner `data` shapes are defined by the owning services' OpenAPI; shown here only as illustration (I).

## 4. Proxied endpoints
Public path = `/api/<svc>` + upstream path. Request/response bodies are defined by the owning service's OpenAPI; the gateway adds auth, CSRF, limits, header strip, token mint. Gateway-level behaviors apply to all rows below: 401/403/404/405/413/415/422/429/5xx per section 2.

Legend: Idem = `Idempotency-Key` required (else 400 `IDEMPOTENCY_KEY_REQUIRED`); CSRF+S = single-use token purpose in brackets; $ = money route (subject to `PS_APIGATEWAY_MONEY_ROUTES_ENABLED`; no gateway retry without Idem; 409 passed through).

| method | public path | roles | CSRF | Idem | notes / upstream events |
|---|---|---|---|---|---|
| POST | `/api/mandate/mandates` | B | +S [mandate_sign] | yes | mandate consumes its own nonce (C4). Upstream event `mandate.signed` |
| GET | `/api/mandate/mandates/{id}` | B,M,O | - | - | ownership by owner service |
| GET | `/api/mandate/mandates/{id}/terms` | B,M,O | - | - | |
| POST | `/api/mandate/mandates/{id}/revoke` | B | +S [mandate_revoke] | optional | idempotent upstream. Event `mandate.revoked` |
| GET | `/api/catalog/items`, `/api/catalog/items/{id}` | B,M,O | - | - | descriptions are untrusted text |
| POST | `/api/agent/propose` | B | general | yes | RL llm + global budget (429 `LLM_BUDGET_EXHAUSTED`). Event `cart.proposed` |
| POST | `/api/checkout/carts` | B | general | yes | forbidden money keys. Event `cart.checked` |
| POST | `/api/checkout/carts/{id}/confirm` | B | +S [order_confirm] | yes | $. Event `order.created` |
| POST | `/api/checkout/orders/{id}/capture` | B | general | yes | $. Body: opaque `state`, `token`, `PayerID`. Events `order.captured` / `order.capture_failed` |
| GET | `/api/checkout/orders/{id}`, `/api/checkout/orders?mandate_id=` | B,M,O | - | - | `approval_url` host-checked (REQ-GW-037) |
| POST | `/api/tracking/shipments` | M | general | yes | Event `shipment.created` |
| GET | `/api/tracking/shipments/{order_id}` | B,M,O | - | - | payload labelled SIMULATED CARRIER (upstream) |
| POST | `/api/tracking/demo/clock/advance` | O | general | - | `PS_APIGATEWAY_DEMO_MODE` only, else 404 |
| POST | `/api/tracking/demo/shipments/{id}/force` | O | general | - | `PS_APIGATEWAY_DEMO_MODE` only, else 404 |
| POST | `/api/resolution/cases/report` | B | general | yes | RL llm; free text untrusted, length cap. Events `case.opened`, `case.triaged` |
| GET | `/api/resolution/cases/{id}`, `/api/resolution/cases?status=` | B (own), M, O | - | - | list is M/O only (else 403) |
| POST | `/api/resolution/offers/{id}/accept` | B | +S [offer_accept] | yes | $. Events `refund.requested`, `refund.completed|failed|unknown`, `case.resolved` |
| POST | `/api/resolution/approvals/{token}/consent` | B | +S [approval_consent] | yes | $. token in path never logged; `act.auth_method=session+approval_token`. Event `approval.granted` |
| POST | `/api/resolution/cases/{id}/merchant-action` | M | general | yes | creates NEW offer (needs buyer approval). Event `offer.created` |
| GET | `/api/audit/entries`, `/api/audit/verify` | B,M,O | - | - | public-safe fields are upstream's job |

Not routed (404): `/mandates/{id}/evaluate`, `/prices/resolve`, `/intent-fit`, `/detector/run`, `/refunds/reconcile`, `/append`, `/internal/*`, paypal-adapter, triage-ai, MCP, any tracker status mutation (PayPal PATCH allows only CANCELLED, V; carrier state is ours).

### 4.1 Worked examples (illustrative bodies; real schemas come from the owning services)
Mandate sign:
```json
GET  /api/auth/csrf?purpose=mandate_sign          -> 200 {"csrf_token":"v1.mandate_sign...."}
POST /api/mandate/mandates
Headers: Origin: https://<web-origin>, X-CSRF-Token: v1.mandate_sign..., Idempotency-Key: 5b0d...-uuid
Body:    {"merchant_allowlist":["<merchant_id>"],"intent_text":"birthday gift for a runner under $60","expires_at":"<iso8601>"}
Note: max total and protection terms are fields of the mandate itself (owner schema), not forbidden money keys on this route (I: allowed-key list per route is set in routing/table.py).
201 {"mandate_id":"<uuid>","mandate_hash":"<sha256>","status":"ACTIVE"}
403 {"error":"CSRF_REPLAYED","message":"Token already used","request_id":"..."}
400 {"error":"IDEMPOTENCY_KEY_REQUIRED",...}
```
Capture after PayPal return (the static web route calls this with the cookie; if cookie is missing the UI shows "sign in again" and never auto-captures):
```json
POST /api/checkout/orders/<order_id>/capture
Headers: Idempotency-Key: <uuid>, X-CSRF-Token: <general>
Body:    {"state":"<opaque>","token":"<opaque>","PayerID":"<opaque>"}
200/201 {"order_id":"<uuid>","state":"CAPTURED","capture_id":"<server-derived>","custom_id":"<mandate_id>"}   (custom_id survives to capture, V)
409     {"error":"CAPTURE_IN_PROGRESS",...}      (upstream-defined code, passed through, never retried)
503     {"error":"MONEY_ROUTES_DISABLED",...}
422     {"error":"CLIENT_MONEY_FIELD_REJECTED","details":{"keys":["amount"]},...}
```
Offer accept:
```json
POST /api/resolution/offers/<offer_id>/accept   (Idempotency-Key + X-CSRF-Token [offer_accept])
Body: {}
200 {"case_id":"<uuid>","state":"REFUNDING"}
409 in-progress passthrough | 422 upstream-mapped (e.g. refund above remaining) | 503 MONEY_ROUTES_DISABLED
```
Cold start:
```json
503 {"error":"UPSTREAM_WAKING","message":"Server is waking up, retry shortly","request_id":"..."}   Retry-After: <seconds>
```
UI shows the "waking server" state and retries only idempotent calls.

## 5. Idempotency summary
- Public header `Idempotency-Key` (client uuid) is passed through unchanged to the owning service, which maps it to its own store and to `PayPal-Request-Id` where applicable (distinct things, agent-context-map glossary).
- Gateway retries (backoff, within total budget): GET always; POST only with `Idempotency-Key`; only on connect error, timeout, 502, 503. Never on 409, never on money POST without a key (that request is refused with 400 first).
- On upstream 401 from clock skew: re-mint once with fresh `iat`, retry idempotent calls only.

## 6. Rate-limit classes (starting values I; tune after load test)
auth 10/min IP; auth-login stricter, IP+handle (value set in implementation); llm 6/min session + global daily counter; sensitive 5/min session; write (value set in implementation); read 120/min session; tick 30/min IP; health generous. In-memory, single instance, resets on restart/sleep (R7).

## 7. Open items affecting this API
- C6 freeze-flag owner; C9 list endpoints for BFF (`buyer-home` cut if absent); C16 `approval_url` host allowlist (week-1 spike); allowed-body-key list per route to be finalized with each owner's OpenAPI; error code names for upstream 409s belong to the owning services.
