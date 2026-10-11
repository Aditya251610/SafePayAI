# paypal-adapter: technical spec

Date: 2026-10-10. Labels: V verified (our sandbox spike 2026-10-10), VC vendor/secondary, I inference/unverified. Python 3.12, FastAPI, Pydantic v2 (`extra="forbid"`), httpx (async), SQLAlchemy 2 + Alembic. No credentials appear in this document; env var NAMES only.

## 1. Architecture
```
checkout | tracking | resolution --(internal service JWT, aud=paypal-adapter)--> paypal-adapter
                                                                                  |- REST  /v1/*
                                                                                  |- MCP   /mcp  (streamable HTTP)
                                                                                  |   both call the same `ops` functions
                                                                                  |- ledger (Postgres schema `paypal`)
                                                                                  '-> PayPal sandbox REST (only egress)
paypal-adapter --(outbox, HTTP push)--> audit
```
- Layers (kept thin, no DDD ceremony: this is a transaction-script anti-corruption layer):
  - `transport`: FastAPI routers + MCP tool registrations; both only parse, authenticate, authorize, then call `ops`.
  - `ops`: one function per tool (authz checks, ticket verify, ledger, PayPal call, normalize). The ONLY place money logic exists, so REST and MCP cannot diverge.
  - `paypal_client`: httpx wrapper (token cache, 401 retry-once, header handling, error mapping). Imports nothing from `ops`.
  - `store`: ledger, nonces, flags, outbox.
- Dependency direction: transport -> ops -> {paypal_client, store, tickets}. `paypal_client` knows nothing of tickets or callers.
- Profile B: runs as the `paypal` process via `hosts/paypal.py`, ALWAYS reached over HTTP by other services (never mounted in-process with them) so the secret stays in its own process env.

## 2. Verified PayPal sandbox facts this service relies on (V, spike 2026-10-10)
- OAuth client-credentials works; `expires_in` ~32,000 s (~9 h); invalid token -> 401.
- Orders v2 create; replay with the same `PayPal-Request-Id` returns the SAME order. New order status PAYER_ACTION_REQUIRED; buyer approves on PayPal sandbox page (redirect to return_url with `token`, `PayerID`); then APPROVED; capture returns 201 COMPLETED.
- `custom_id` and `invoice_id` on the purchase unit survive onto the capture.
- Tracking: `POST /v2/checkout/orders/{id}/track` (capture_id, tracking_number, carrier OTHER + carrier_name_other, notify_payer) -> 201; tracker id = `{capture_id}-{tracking_number}`; default status SHIPPED; multiple trackers per capture OK. PATCH `/status` works ONLY for CANCELLED (204) and is irreversible (`CANNOT_PATCH_CANCELLED_TRACKER` afterwards); PATCH to ON_HOLD/SHIPPED/DELIVERED -> 400 `INVALID_PARAMETER_VALUE`; `status` at creation is accepted but ignored.
- Refunds: `POST /v2/payments/captures/{id}/refund` partial -> 201 COMPLETED; second partial OK; capture then reads PARTIALLY_REFUNDED; same Request-Id replay returns the original refund (even if the amount differs); real over-refund -> 422 `REFUND_AMOUNT_EXCEEDED`; reused `invoice_id` -> 422 `DUPLICATE_INVOICE_ID`; two concurrent identical refunds (same Request-Id) -> one 201 and one 409; `GET /v2/payments/refunds/{id}` works.
- Account: Merchant-type REST app on an India-based sandbox business account; USD orders work; India-based buyer cannot pay in USD; US personal buyer works.

## 3. REST-to-tool mapping (exact verified calls)
Base: `PS_PAYPALADAPTER_PAYPAL_BASE_URL` (sandbox host only). Class: READ / WRITE / MONEY. "Ticket" = authorization ticket required.

| Tool | Class | Internal REST | PayPal call | Verified request/response facts | Ticket | Idempotency |
|---|---|---|---|---|---|---|
| create_order | MONEY | `POST /v1/orders` | `POST /v2/checkout/orders` | intent CAPTURE; amount from ticket-matched `amount_minor`+currency; purchase unit `custom_id`=mandate_id, `invoice_id`=internal order id (V survive onto capture); returns id, status PAYER_ACTION_REQUIRED, approve link (V). Exact JSON placement of return/cancel URL: copy from the spike script (I until pinned in a fixture) | yes (op create_order) | `PayPal-Request-Id` = `request_id`; replay returns same order (V) |
| get_order | READ | `GET /v1/orders/{id}` | `GET /v2/checkout/orders/{id}` | status transitions PAYER_ACTION_REQUIRED -> APPROVED -> COMPLETED observed (V); full field shape beyond status/amount/custom_id/capture ids (I) | no | n/a |
| capture_order | MONEY | `POST /v1/orders/{id}/capture` | `POST /v2/checkout/orders/{id}/capture` | after buyer approval: 201 COMPLETED (V); before approval PayPal returns an error (exact name unverified, I) -> we map to `ORDER_NOT_APPROVED` after our own pre-check | yes (op capture_order) | Request-Id = `request_id` |
| get_capture | READ | `GET /v1/captures/{id}` | `GET /v2/payments/captures/{id}` | reads COMPLETED / PARTIALLY_REFUNDED (V); `custom_id`/`invoice_id` present (V); whether the payload exposes total refunded (I) so `refundable_remaining` is DERIVED = captured - sum(our refund_ledger COMPLETED/PENDING) and labelled `derived` | no | n/a |
| add_tracking | WRITE | `POST /v1/orders/{id}/track` | `POST /v2/checkout/orders/{id}/track` | body: capture_id, tracking_number, carrier `OTHER`, carrier_name_other, notify_payer (default false); 201 (V); tracker id `{capture_id}-{tracking_number}` (V); NEVER send `status` (ignored, V) | no (WRITE, not money) | `request_id` as Request-Id (header effect on this endpoint: I) + natural key (capture_id, tracking_number) in ledger; duplicate returns existing |
| get_tracking | READ | `GET /v1/orders/{id}/trackers/{tracker_id}` | tracker GET (path UNVERIFIED, I) | default status SHIPPED (V at creation). Carrier late/lost lives in OUR `tracking` DB, merged and labelled `SIMULATED` | no | n/a |
| refund_capture | MONEY | `POST /v1/captures/{id}/refund` | `POST /v2/payments/captures/{id}/refund` | partial refund body `amount{currency_code,value}`, optional `invoice_id`, static `note_to_payer`; 201 COMPLETED (V); replay same Request-Id -> original refund even if amount differs (V); 422 REFUND_AMOUNT_EXCEEDED, 422 DUPLICATE_INVOICE_ID, 409 concurrent (V) | yes (op refund_capture) | Request-Id = `request_id` (persisted by resolution BEFORE the call, ADR-011); adapter ledger enforces body-hash equality |
| get_refund | READ | `GET /v1/refunds/{id}` | `GET /v2/payments/refunds/{id}` | works (V) | no | n/a |

Not exposed (deliberate): tracker PATCH (irreversible CANCELLED, V), order PATCH, void/authorize, payouts, vault, disputes.

## 4. Verified vs UNVERIFIED (kept separate)

### 4.1 Verified (V) behaviors the contract tests must replay
See section 2. Test-plan maps each to a test ID.

### 4.2 UNVERIFIED (I). Each has a design fallback; none may be claimed.
| # | Behavior | Why it matters | Fallback until verified | Verification action (sprint) |
|---|---|---|---|---|
| U1 | Refund returning `PENDING` | status model, "refund done" semantics | enum has PENDING; callers treat as non-final and reconcile with get_refund; fake PayPal can emit it | Try to provoke in sandbox (S3); record result |
| U2 | Tracker GET path and payload | get_tracking tool | derived tracker id + `unverified` flag, SIMULATED carrier status | one-call spike (S2) |
| U3 | Webhook signature verification and delivery to a sleeping host | optional ingestion | default OFF; hint only; if enabled, re-fetch and ignore signature result as authority | spike only if time (S4, cut first) |
| U4 | Real return URL (`token`, `PayerID`) landing on OUR server | checkout flow (owned by checkout/gateway, adapter only validates the return_url origin it is given) | checkout owns; adapter just creates order with given URLs | test in week 1 with the host URL (deployment doc) |
| U5 | Order GET / capture GET full field shapes | DTO mapping | Pydantic models parse only needed fields, ignore rest | capture fixtures from live sandbox (S1/S2) |
| U6 | PayPal Request-Id retention window | replay after long gap | local ledger serves replays regardless | unknown; note |
| U7 | PayPal rate limits / 429 behavior | backoff | conservative concurrency cap, honor `Retry-After` | unknown |
| U8 | Error name when capturing a not-yet-approved order | `ORDER_NOT_APPROVED` mapping | our pre-check via get_order catches it first | observe once (S2) |
| U9 | `PayPal-Request-Id` accepted on tracking POST and its effect | tracking idempotency | rely on natural-key ledger | observe (S2) |
| U10 | `paypal-debug-id` header name/presence | log correlation | log if present | observe |
| U11 | MCP Python SDK mount API / stateless HTTP mode | transport | hand-written JSON-RPC handler | spike S1 |
| U12 | Disputes API / simulator | out of scope | none | not planned |

## 5. Authorization tickets (money tools)

### 5.1 Why
- Defense in depth for confused-deputy: even a caller with the right JWT cannot create/capture/refund unless the owning service minted a ticket for exactly these parameters. LLM-facing services have no JWT scope for the adapter and no minting key (agent-and-mcp section 3, auth-gateway section 3.2).
- Honest limit: HMAC keys are server-held (demo-grade). Not non-repudiation.

### 5.2 Format
`ticket = b64url(payload_json) + "." + b64url(HMAC_SHA256(key[kid], "ps-ticket-v1." + b64url(payload_json)))`

Payload (canonical JSON, sorted keys, UTF-8, integer minor units):
| field | meaning |
|---|---|
| `v` | 1 |
| `kid` | key id (rotation) |
| `tid` | uuid4, single-use id |
| `iss` | `checkout` or `resolution` |
| `aud` | `paypal-adapter` |
| `op` | `create_order` / `capture_order` / `refund_capture` |
| `mandate_id` | must equal order `custom_id` / capture `custom_id` |
| `proposal_hash` | from checkout cart / resolution refund proposal |
| `subject` | create_order: internal order id (becomes `invoice_id`); capture_order: PayPal order id; refund_capture: capture id |
| `amount_minor`, `currency` | exact amount authorized (ceiling-equal; adapter requires `amount_minor` in the call to equal it) |
| `request_id` | the PayPal-Request-Id this ticket authorizes (binds ticket to one intent) |
| `iat`, `exp` | epoch seconds |
Header on REST: `X-Authorization-Ticket`; MCP: tool argument `authorization_ticket` (opaque string, not a nested object; supersedes the nested form in agent-and-mcp, see section 14).

### 5.3 TTL
- Default `PS_PAYPALADAPTER_TICKET_TTL_SECONDS` (default (I), set in config, intended to be short: minutes not hours; tuned in S2). Verifier allows small clock skew (`PS_PAYPALADAPTER_TICKET_SKEW_SECONDS`, default (I)). Clock matters on free tiers; use platform NTP.
- Minter must re-read mandate state (not revoked/expired) at minting time. A ticket cannot see later revocation, so TTL is kept short AND the adapter checks the freeze flag; the owning service's own final pre-call check (resolution check list; checkout capture re-check) remains authoritative.

### 5.4 Verification order (all must pass; first failure rejects, fail closed)
1. Caller JWT valid, `aud=paypal-adapter`, `sub` in allowlist for the tool (else `NOT_PERMITTED`).
2. Ticket structure valid, `v=1`, `kid` known, HMAC constant-time equal using key for `iss` (checkout key only verifies `iss=checkout`).
3. `iss` matches JWT `sub` and is permitted to mint `op` (checkout: create_order, capture_order; resolution: refund_capture).
4. `aud` correct; `exp` not passed (with skew); `op` equals the tool being called.
5. Call parameters equal ticket: `mandate_id`, `proposal_hash` (supplied by caller), `subject`, `amount_minor`, `currency`, `request_id`.
6. Single use: `INSERT INTO ticket_nonces(tid, request_id, body_hash, created) ... ON CONFLICT DO NOTHING`; if the row existed, only allowed when the stored `request_id` and `body_hash` equal this call (a retry of the same intent), in which case the call is served from the ledger and PayPal is NOT called again. Otherwise `TICKET_REPLAYED`.
7. Kill switch: `PS_PAYPALADAPTER_MONEY_ENABLED` true AND DB freeze flag clear (else `MONEY_FROZEN`).
8. Op-specific invariants:
   - create_order: `custom_id` := ticket.mandate_id, `invoice_id` := ticket.subject; return/cancel URL origins in `PS_PAYPALADAPTER_PAYPAL_RETURN_URL_ALLOWED_ORIGINS`.
   - capture_order: `get_order` status APPROVED, `custom_id` == mandate_id, amount/currency == ticket (else `AUTHORIZATION_MISMATCH` / `ORDER_NOT_APPROVED`).
   - refund_capture: `get_capture` -> `custom_id` == mandate_id, currency equal, `amount_minor` <= `PS_PAYPALADAPTER_REFUND_MAX_MINOR` (config ceiling) and <= derived refundable_remaining; `invoice_id` if supplied must not be reused (PayPal enforces, V).
9. Only then write ledger IN_FLIGHT and call PayPal.
- Failure codes: `TICKET_INVALID`, `TICKET_EXPIRED`, `TICKET_REPLAYED`, `AUTHORIZATION_MISMATCH`, `NOT_PERMITTED`, `MONEY_FROZEN`.
- Keys: `PS_CHECKOUT_TICKET_HMAC_KEY`, `PS_RESOLUTION_TICKET_HMAC_KEY` (names only; named after the minting service, consumed here). The minter service holds only its own key; the adapter holds both for verification (symmetric: a compromised adapter could forge; accepted for demo and disclosed). `kid` rotation: accept {current, previous}.

## 6. Idempotency and the ledger
- Table `call_ledger(request_id PK, op, caller, ticket_tid, body_sha256, state, paypal_http_status, paypal_object_id, response_json_redacted, created, updated)`; states: IN_FLIGHT -> DONE(OK|REJECTED) | UNKNOWN | IN_PROGRESS_REMOTE.
- Table `refund_ledger(refund_id, request_id, capture_id, amount_minor, currency, status, created)` for derived refundable_remaining and reconciliation.
- Flow (write): validate -> insert ledger IN_FLIGHT (unique request_id; conflict handling below) -> call PayPal -> update ledger -> emit outbox event.
- Conflict handling on insert:
  - existing DONE and same `body_sha256` -> return stored response with `replayed=true` (no PayPal call).
  - existing DONE/any and different `body_sha256` -> `IDEMPOTENCY_KEY_REUSED` (REJECTED). This is OUR guard because PayPal returns the original even when the amount differs (V).
  - existing IN_FLIGHT (local concurrent duplicate) -> `IN_PROGRESS` without calling PayPal.
  - existing UNKNOWN -> return `UNKNOWN` again; caller reconciles with get_*; it never re-sends under a new request_id for the same intent.
- PayPal 409 -> ledger state IN_PROGRESS_REMOTE, return `IN_PROGRESS` (V behavior).
- Timeout/5xx on write -> ledger UNKNOWN. Optional `POST /v1/reconcile/{request_id}` resolves by lookup (get_order / get_capture / get_refund).
- `request_id`: UUID, caller-generated and persisted before the call (ADR-011). Missing -> 422 `REQUEST_ID_REQUIRED`.
- Retention: ledger rows kept for the project's life (demo scale); no PayPal retention assumption (U6).

## 7. Error normalization
Envelope for REST and MCP (single shape):
`{ "ok": bool, "status": "OK|IN_PROGRESS|REJECTED|UNKNOWN", "paypal_http_status": int|null, "data": {...}|null, "error": {"code","message","retryable":bool,"paypal_name":str|null}|null, "replayed": bool, "trace_id": str }`

| Source | Our status | Our code | Notes |
|---|---|---|---|
| 2xx | OK | - | |
| 401 from PayPal (after one refresh+retry) | UNKNOWN? no: REJECTED (did not process) | `UPSTREAM_AUTH_FAILED` | ops alert; REST 503 |
| 400 `INVALID_PARAMETER_VALUE` (V, e.g. tracker status PATCH) | REJECTED | `INVALID_PARAMETER` | we never send such calls; guard test |
| 404 | REJECTED | `NOT_FOUND` | |
| 409 on write (V) | IN_PROGRESS | `IN_PROGRESS` | reconcile via GET, never retry blind |
| 422 `REFUND_AMOUNT_EXCEEDED` (V) | REJECTED | `REFUND_AMOUNT_EXCEEDED` | resolution -> HUMAN_REVIEW |
| 422 `DUPLICATE_INVOICE_ID` (V) | REJECTED | `DUPLICATE_INVOICE_ID` | resolution -> HUMAN_REVIEW |
| 422 other | REJECTED | `UPSTREAM_REJECTED` with `paypal_name` | |
| 429 (I) | READ: retried with backoff; WRITE: UNKNOWN-safe? REJECTED not processed assumed (I) -> treat as `UNKNOWN` to be safe | `RATE_LIMITED` | conservative |
| 5xx / timeout / connection reset on write | UNKNOWN | `UPSTREAM_UNAVAILABLE` | ledger UNKNOWN |
| 5xx / timeout on read | REJECTED (retryable) after bounded retries | `UPSTREAM_UNAVAILABLE` | |
| Our own checks | REJECTED | `NOT_PERMITTED`, `TICKET_*`, `AUTHORIZATION_MISMATCH`, `MONEY_FROZEN`, `REQUEST_ID_REQUIRED`, `IDEMPOTENCY_KEY_REUSED`, `ORDER_NOT_APPROVED`, `AMOUNT_OVER_CEILING`, `CURRENCY_UNSUPPORTED`, `VALIDATION_ERROR` | |
- PayPal error `message` bodies are untrusted text: truncated, stripped of control chars, never forwarded to models; callers get our code + fixed message.
- HTTP mapping for REST: OK 200/201; IN_PROGRESS 202; REJECTED 400/403/404/409/422 by code; UNKNOWN 504; upstream-down on read 502/503.

## 8. Rate limiting and backoff
- Inbound: per-caller token bucket in memory (`PS_PAYPALADAPTER_RATE_LIMIT_READ_PER_MIN`, `PS_PAYPALADAPTER_RATE_LIMIT_MONEY_PER_MIN`; values (I) set in config and tuned; single instance only, resets on restart). Exceed -> 429 `RATE_LIMITED_INBOUND` + `Retry-After`; audited.
- Outbound: global concurrency semaphore (`PS_PAYPALADAPTER_PAYPAL_MAX_CONCURRENCY`); timeouts per call (`PS_PAYPALADAPTER_PAYPAL_TIMEOUT_SECONDS`); GET retries with exponential backoff + jitter, bounded attempts (`PS_PAYPALADAPTER_PAYPAL_GET_RETRIES`), honoring `Retry-After`. Writes: no retries except the single 401 retry after token refresh. No polling loops inside the adapter (Render outbound-traffic suspension risk, V).
- PayPal's own limits unknown (U7).

## 9. Token cache and sandbox guard
- Token: memory only, struct {access_token, expires_at}. Refresh when `now >= expires_at - PS_PAYPALADAPTER_PAYPAL_TOKEN_REFRESH_SKEW_SECONDS` (default (I)), single-flight (asyncio lock). 401 -> invalidate, refresh once, retry the identical request once (same Request-Id), then give up with `UPSTREAM_AUTH_FAILED`. Process restart/sleep = cold token fetch.
- Startup guard (`app.startup`):
  1. `PS_PAYPALADAPTER_PAYPAL_MODE` must equal `sandbox`.
  2. Parse `PS_PAYPALADAPTER_PAYPAL_BASE_URL`; scheme `https`; host must equal the constant `api-m.sandbox.paypal.com` (also the threat-model egress allowlist); no userinfo, no port override, no path other than empty.
  3. Fail -> log a non-secret reason and `sys.exit(1)`; `/readyz` reports `sandbox_guard: pass`.
  4. HTTP client created with `base_url` fixed and redirects disabled; request URLs built only from fixed path templates + validated IDs (regex `^[A-Za-z0-9_-]{1,64}$`) so no caller string can alter host/path.
- Credentials never logged; `repr()` of config masks them.

## 10. Logging redaction
- Structured JSON logs: `service, trace_id, tool, caller, request_id_hash, ticket_tid, paypal_http_status, status, latency_ms, paypal_debug_id?`.
- Redact (filter + unit test with canary values): `Authorization`, `Cookie`, client secret, access token, `X-Authorization-Ticket`/ticket strings, `token`, `PayerID`, `approve` link query, payer name/email/address from PayPal responses, request bodies except allowlisted fields (amount, currency, ids), `note_to_payer`.
- Ledger `response_json_redacted` stores only allowlisted fields (ids, status, amounts, custom_id, invoice_id).
- Full request/response bodies never logged in non-debug; debug flag is off by default and must not be set in the deployed env.

## 11. MCP server
- Library: Python MCP SDK (FastMCP) mounted at `/mcp` on the same FastAPI app (I: verify mount API, U11). Transport: streamable HTTP, stateless mode preferred so sleep/restart loses nothing (I).
- Auth: ASGI middleware before the MCP app verifies the internal service JWT (EdDSA pinned, `aud=paypal-adapter`, short exp, `kid` from trusted keys). No/invalid -> 401. Caller identity placed in a contextvar; tools read it, never take a caller id from arguments.
- Allowlist enforced at `tools/list` (filtered) and again at `tools/call` (`NOT_PERMITTED`), independent of the client.
- Tools share `ops` with REST: same ticket/ledger path (one money path). Tool results are the common envelope inside `structuredContent` plus a short text. `isError=true` when `ok=false`.
- Not exposed via `api-gateway`. Judges reach it only through the optional demo-inspector token (read-only, off by default) or a local compose run.
- Tool inputs: `additionalProperties: false`, string length caps, ID regexes.
- Resources/prompts: none in v1 (agent-and-mcp lists optional ones; cut).
- Official `@paypal/mcp`: OPTIONAL COMPARISON ONLY. Exists with remote sandbox endpoints, tokens up to ~8 h (V per PayPal docs read earlier); NOT tested from a backend (V per brief). Not in runtime or CI. Dev notebook lists its tools next to ours to show we expose a least-privilege subset with ticket gating and our own ledger. No claim it is inferior.

## 12. Config / env names (names only, never values)
| Name | Purpose | Secret |
|---|---|---|
| `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` | OAuth client credentials | yes (this service only; deliberate exception to `PS_<SLUG>_*` — exact names already used in the working, tested sandbox spike and `.env`, see deployment.md) |
| `PS_PAYPALADAPTER_PAYPAL_MODE` | must be `sandbox` | no |
| `PS_PAYPALADAPTER_PAYPAL_BASE_URL` | must be sandbox API https URL | no |
| `PS_PAYPALADAPTER_PAYPAL_TIMEOUT_SECONDS`, `PS_PAYPALADAPTER_PAYPAL_MAX_CONCURRENCY`, `PS_PAYPALADAPTER_PAYPAL_GET_RETRIES`, `PS_PAYPALADAPTER_PAYPAL_TOKEN_REFRESH_SKEW_SECONDS` | client tuning | no |
| `PS_PAYPALADAPTER_PAYPAL_RETURN_URL_ALLOWED_ORIGINS` | allowed origins for return/cancel URLs | no |
| `PS_PAYPALADAPTER_DATABASE_URL` | `paypal_app` role, schema `paypal` only | yes |
| `PS_PAYPALADAPTER_INTERNAL_JWKS_URL` (optional), `PS_PAYPALADAPTER_INTERNAL_TRUSTED_ISSUERS` (static JSON of kid->public key) | verify internal JWTs | public keys, not secret |
| `PS_PAYPALADAPTER_SERVICE_NAME` (=paypal-adapter), `PS_PAYPALADAPTER_INTERNAL_JWT_AUD` | token audience | no |
| `PS_CHECKOUT_TICKET_HMAC_KEY`, `PS_RESOLUTION_TICKET_HMAC_KEY`, `PS_CHECKOUT_TICKET_HMAC_KID`, `PS_RESOLUTION_TICKET_HMAC_KID` | ticket verification; named after the minting service (checkout/resolution), consumed here | yes |
| `PS_PAYPALADAPTER_TICKET_TTL_SECONDS`, `PS_PAYPALADAPTER_TICKET_SKEW_SECONDS` | ticket limits | no |
| `PS_PAYPALADAPTER_MONEY_ENABLED` | kill switch (fail closed if unset/unparseable) | no |
| `PS_PAYPALADAPTER_REFUND_MAX_MINOR` | per-call refund ceiling | no |
| `PS_PAYPALADAPTER_CALLER_ALLOWLIST_JSON` (optional override; default compiled in) | caller->tools | no |
| `PS_PAYPALADAPTER_RATE_LIMIT_READ_PER_MIN`, `PS_PAYPALADAPTER_RATE_LIMIT_MONEY_PER_MIN` | inbound limits | no |
| `PS_PAYPALADAPTER_AUDIT_PUSH_URL`, `PS_PAYPALADAPTER_OUTBOX_FLUSH_SECRET` | event push / cron flush | secret for flush |
| `PS_PAYPALADAPTER_WEBHOOK_ENABLED` (default false), `PS_PAYPALADAPTER_PAYPAL_WEBHOOK_ID` | optional webhooks | id not secret |
| `PS_PAYPALADAPTER_DEMO_INSPECTOR_ENABLED` (default false) | read-only demo token acceptance | no |
| `PS_PAYPALADAPTER_LOG_LEVEL`, `PS_PAYPALADAPTER_TRACE_HEADER` | observability | no |
Forbidden in this env: `LLM_API_KEY`, session/CSRF/mandate/approval keys (CI manifest test). `.env.example` lists names with placeholder text only.

## 13. Events (outbox + HTTP push to audit; envelope per overview section 7)
- `paypal.call_recorded` (service-map). Proposed additions (need service-map/contract owner approval, section 14): `paypal.call_denied` (allowlist/ticket rejection), `paypal.hint_received` (webhook hint). Payload in api.md.
- Outbox table in schema `paypal` (service-map lists call_ledger/refund_ledger only; outbox added, ADR-003 requires it).

## 14. Conflicts and recommendations (service-map.md and adr.md win; recorded, others' files not edited)
| # | Conflict | Sources | Resolution here / recommendation |
|---|---|---|---|
| C1 | Signed ticket vs callback validation | agent-and-mcp section 3 lists both ("ship ticket HMAC or call back"); auth-gateway says adapter "re-verifies a decision_id in the DB" (a callback/DB read, which would breach P4 no cross-schema reads) | RECOMMEND signed ticket (chosen). Reasons: no extra sync hop (max depth 3, overview), works when the owning service sleeps, adapter schema stays private, easy to test offline. Cost: cannot see revocation after minting (short TTL + minter re-read + freeze flag), demo-grade symmetric keys. Optional later hardening: callback to resolution `GET /decisions/{id}` for refunds only if time allows (cut-line COULD). |
| C2 | MCP tool list/names | service-map & ADR-007: 6 tools incl. `refund_capture`; task/agent-and-mcp: 8 tools incl. `refund_capture`, `get_capture`, `get_tracking` | Implement the 8 (superset). `refund_capture` accepted as a deprecated alias for `refund_capture` in code but not listed. service-map owner should update its tool list. |
| C3 | Idempotency field name | service-map: `request_id`; agent-and-mcp: `idempotency_key` | Use `request_id` (service-map wins). |
| C4 | Caller identity | agent-and-mcp: per-caller bearer tokens, names `checkout-svc`, `merchant-svc`; auth-gateway/ADR-006: EdDSA internal JWT, trusted-issuer map or cached JWKS | Use ADR-006 JWT; caller = JWT `sub` = final slug (`checkout`, `tracking`, `resolution`). `merchant-svc` does not exist; `tracking` owns add_tracking. Verifier uses static `PS_PAYPALADAPTER_INTERNAL_TRUSTED_ISSUERS` with optional JWKS refresh (avoids cold-start dependency on the gateway). Service-originated calls are self-issued by the calling service (auth-gateway 3.1); the adapter does NOT accept gateway-minted user tokens. |
| C5 | Who calls add_tracking | service-map adapter line: "checkout: orders/capture/track"; dependency graph and tracking section: tracking -> paypal-adapter | Allowlist gives add_tracking/get_tracking to `tracking` only (least privilege, matches graph). Service-map line 74 should be corrected. |
| C6 | Kill switch | auth-gateway: env `PS_PAYPALADAPTER_MONEY_ENABLED`; threat-model: DB row `REFUNDS_FROZEN`, default frozen if unreadable, read by resolution AND adapter | Implement both in adapter; frozen if either blocks. DB flag stored in the adapter's own schema (`paypal.control_flags`), set via operator-only endpoint; resolution check #1 reads it through `GET /v1/control/status` (no cross-schema SQL). Threat-model's wording of a shared row conflicts with P4/ADR-004. |
| C7 | Ticket carries objects vs opaque | agent-and-mcp nested `authorization_ticket{mandate_id, proposal_hash}` | Opaque signed string; call args carry the same fields for comparison. |
| C8 | Health path | overview: `/healthz` `/readyz`; deployment-zero-cost: `/health` | Use `/healthz` and `/readyz`; also serve `/health` alias for pingers. |
| C9 | Webhook receiver location | auth-gateway route table sends `/webhooks/paypal` to orchestrator via gateway; adapter is the credential holder | Optional: receiver in adapter at `/v1/webhooks/paypal`, reached through a gateway pass-through route if enabled; default OFF. Needs gateway owner decision. |
| C10 | Event additions | service-map lists one adapter event | Propose `paypal.call_denied`, `paypal.hint_received`; if rejected, fold denials into `paypal.call_recorded` with `status=DENIED`. |
| C11 | Service names in older docs (`orchestrator`, `carrier-sim`, `policy`, `mcp`, `ai-service`) | auth-gateway, agent-and-mcp | Map to final slugs: checkout/resolution, tracking, resolution, paypal-adapter, shopping-agent+triage-ai. `llm-gateway` is not a service. |
| C12 | Outbox ownership | service-map: adapter owns call_ledger, refund_ledger only | Add `outbox`, `ticket_nonces`, `control_flags` tables to `paypal` schema. |
| C13 | Over-refund and "capture amount" rules | agent-and-mcp: `refundable_remaining` from get_capture | PayPal capture payload may not expose it (U5); derive from refund_ledger and rely on PayPal 422 backstop (V). |

## 15. Claims (service-level)
May say: "only service with PayPal credentials", "sandbox-only guard", "idempotent via PayPal-Request-Id (V) plus local ledger", "own MCP server over verified REST calls", "demo-grade HMAC authorization tickets".
Must not say: official PayPal MCP, PayPal-backed/verified, non-repudiable, production-secure, injection-proof, real money, or that refund PENDING/webhooks/tracker GET are verified.
