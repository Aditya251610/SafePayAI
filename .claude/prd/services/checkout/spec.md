# checkout: spec

Labels: V verified in our 2026-10-10 sandbox spike, VC vendor claim, I inference/unverified. Follows `service-map.md` and `adr.md`. Conflicts in section 12.

## 1. Position
- Slug `checkout`. Profile B process `core` (with mandate, catalog, tracking, resolution, audit); Profile A separate process. Code boundary identical in both (P7).
- Sync calls (downward only): catalog `/prices/resolve`, mandate `/evaluate` + `GET /mandates/{id}`, shopping-agent `/intent-fit` (advisory), paypal-adapter.
- Never calls: audit directly (outbox push only), tracking, resolution, any LLM, PayPal.
- Auth: verifies internal JWT (EdDSA, `aud=checkout`, ADR-006). Identity only from token `sub`/`role`; no identity in body.

## 2. Tables owned (schema `checkout`, role `checkout_app`, no cross-schema SQL)
All money in integer minor units; currency `USD` only (I: demo scope).

| Table | Key columns | Notes |
|---|---|---|
| `carts` | `cart_id` uuid pk, `buyer_id`, `mandate_id`, `mandate_hash`, `status` (CHECKED, BLOCKED, NEEDS_CONFIRMATION, CONFIRMED, SUPERSEDED, EXPIRED), `lines` jsonb [{sku, qty, unit_minor, line_minor, merchant_id}], `total_minor`, `currency`, `merchant_ids`, `catalog_version`, `proposal_hash`, `intent_fit_verdict`, `intent_fit_reason_code`, `intent_fit_confidence`, `stated_price_mismatch` bool, `committed_minor_at_check`, `created_at` | Prices copied from catalog at check time; never from client/model |
| `cart_checks` | `id`, `cart_id`, `phase` (CHECK, CONFIRM), `name`, `result` (PASS, BLOCK, TIGHTEN, SKIPPED), `reason_code`, `detail`, `source` (mandate, catalog, checkout, intent_fit), `ts` | Receipt "checks list" is read from here. Append-only by convention |
| `orders` | `order_id` uuid pk, `cart_id` uniq, `buyer_id`, `mandate_id`, `status` (s3), `total_minor`, `currency`, `paypal_order_id` uniq nullable, `create_request_id` uuid, `capture_request_id` uuid, `custom_id`, `invoice_id`, `approve_url`, `last_paypal_status`, `failure_code`, `version` int, `created_at`, `updated_at` | `custom_id = mandate_id`; `invoice_id = order_id` (V: both survive onto capture). Optimistic `version` for compare-and-swap |
| `captures` | `capture_id` pk, `order_id` uniq, `amount_minor`, `currency`, `paypal_status`, `custom_id`, `invoice_id`, `captured_at` | One row per order; unique(order_id) blocks double capture |
| `receipts` | `order_id` pk, `receipt_json` jsonb, `mandate_hash`, `audit_event_id`, `protection_window_days`, `remaining_cap_minor`, `created_at` | Immutable once COMPLETED; written in same txn as capture row |
| `return_bindings` | `state_hash` pk, `order_id`, `buyer_id`, `mandate_id`, `paypal_order_id`, `kind` (return, cancel), `exp`, `used_at` | Random 128-bit `state` stored as SHA-256 only. TTL 30 min (I, from auth-gateway) |
| `idempotency_keys` | `(buyer_id or system, route, key)` pk, `request_hash`, `response_code`, `response_body`, `created_at` | Replay same body -> stored response; different body -> 422 |
| `inbox` | `event_id` pk, `type`, `received_at` | Dedupe at-least-once events |
| `outbox` | `seq` bigserial, `event_id`, `type`, `aggregate_id`, `payload`, `delivered_at`, `attempts` | ADR-003 |

Constraints that carry safety: unique(`orders.cart_id`), unique(`orders.paypal_order_id`), unique(`captures.order_id`), unique(`orders.invoice_id`), CHECK(`total_minor` > 0), CHECK(currency = 'USD').

## 3. Order state machine
```
              confirm (checks re-run OK)
 cart CONFIRMED ──► CREATING ──► AWAITING_APPROVAL ──► APPROVED ──► CAPTURING ──► CAPTURED (terminal)
                     │  │            │  │                 │  │          │  │
                     │  └► CREATE_UNKNOWN (reconcile)     │  │          │  ├► CAPTURE_PENDING (I) ─► CAPTURED | CAPTURE_FAILED
                     └► CREATE_FAILED (terminal)          │  │          │  ├► CAPTURE_UNKNOWN ─► CAPTURED | CAPTURE_FAILED
                                                          │  │          │  └► CAPTURE_FAILED (terminal)
                                       CANCELLED_BUYER ◄──┘  └► CANCELLED_REVOKED (terminal, no capture attempted)
                                       EXPIRED (terminal): AWAITING_APPROVAL older than order TTL, no capture
```
- Transitions are compare-and-swap on `orders.version` inside a local transaction; the transition is written BEFORE the external call (R4).
- `CREATING`: row + `create_request_id` persisted, then adapter `create_order`. Success -> AWAITING_APPROVAL (PayPal PAYER_ACTION_REQUIRED, V). Timeout/5xx/409/UNKNOWN envelope -> CREATE_UNKNOWN; reconcile replays create with the SAME request id (V: same order returned) after a get attempt; never a new request id for the same order.
- `APPROVED`: reached only after our own re-fetch of the PayPal order shows APPROVED (V) and all comparisons pass; the return redirect alone never moves state.
- `CAPTURING`: `capture_request_id` persisted first; one capture attempt in flight (row lock / CAS).
- Revoke path: mandate revoked/expired detected at return or at pre-capture re-check -> CANCELLED_REVOKED, `order.capture_failed{reason: MANDATE_REVOKED}`. The approved-but-uncaptured PayPal order is left to expire in PayPal (no void API used; I: expiry window unknown).
- Terminal states are immutable.

Cart states: CHECKED (all pass), NEEDS_CONFIRMATION (intent-fit tighten), BLOCKED (any hard block or REJECT_WITH_REASON), CONFIRMED (order created from it), SUPERSEDED (re-check produced a different proposal_hash), EXPIRED.

## 4. Cart check pipeline (`POST /carts`, and re-run at confirm)
1. Authenticate; buyer owns `mandate_id` (ownership check via mandate GET with the token's `buyer_id`; mismatch -> 404).
2. Validate body: `extra=forbid`; lines 1..N, `qty` int >= 1; dedupe SKUs by merging; size limits.
3. catalog `/prices/resolve` -> priced lines, `merchant_id` per line. Unknown SKU or catalog failure -> BLOCK `CATALOG_UNAVAILABLE` / `UNKNOWN_SKU`.
4. If body carried `stated_unit_prices_minor` (from the proposal) and any differs from catalog -> hard block `PRICE_MISMATCH` (checkout-owned check; stated price is never used).
5. Compute `total_minor = sum(qty * unit_minor)` (+ fees_minor only if catalog returns it; I: demo has no shipping/tax). Currency from catalog; must be USD.
6. Compute `committed_minor` = sum of `total_minor` for this mandate's orders in {AWAITING_APPROVAL, APPROVED, CAPTURING, CAPTURE_PENDING, CAPTURE_UNKNOWN, CAPTURED} (I: cap is cumulative per mandate; see s12).
7. mandate `/evaluate` {server-priced cart, committed_minor} -> allow/block + reasons[] (revoked, expired, merchant not allowlisted, cap, unknown SKU, qty cap, currency). Unreachable/timeout/5xx/malformed -> BLOCK `MANDATE_UNAVAILABLE`.
8. Only if steps 3-7 have zero blocks: shopping-agent `/intent-fit` (timeout per config). Failure/timeout/confidence below the agent doc threshold -> NEEDS_BUYER_CONFIRMATION. The verdict is stored with label `advisory=true`.
9. Combination rule (pure function, unit-tested): `status = BLOCKED if any hard block or REJECT; NEEDS_CONFIRMATION if verdict != PASS; else CHECKED`. Nothing moves BLOCKED to allowed.
10. `proposal_hash = SHA-256(canonical JSON {mandate_id, mandate_hash, sorted (sku, qty), total_minor, currency, merchant_ids, policy_version})` (agent-and-mcp s1a). Computed by checkout from validated data.
11. Persist cart + `cart_checks`, outbox `cart.checked`, return reasons.

Reason-code vocabulary (stable, used by UI and tests): `MANDATE_REVOKED, MANDATE_EXPIRED, MERCHANT_NOT_ALLOWED, OVER_CAP, UNKNOWN_SKU, QTY_CAP, CURRENCY_MISMATCH, PRICE_MISMATCH, MANDATE_UNAVAILABLE, CATALOG_UNAVAILABLE, INTENT_FIT_REJECT, INTENT_FIT_NEEDS_CONFIRMATION, INTENT_FIT_UNAVAILABLE, CART_CHANGED`.

## 5. Order creation (`POST /carts/{id}/confirm`)
1. `Idempotency-Key` required. Cart must be CHECKED or NEEDS_CONFIRMATION; if NEEDS_CONFIRMATION body must carry `confirm_intent_fit=true`.
2. Re-run section 4 steps 3-10 fresh. New `proposal_hash` != body `proposal_hash` -> 409 `CART_CHANGED`, cart SUPERSEDED. Any block -> 422 with reasons.
3. In one transaction: insert `orders` (CREATING, `create_request_id` = uuid4, `custom_id = mandate_id`, `invoice_id = order_id`), `return_bindings` (return and cancel `state`), outbox nothing yet.
4. Mint `authorization_ticket` (HMAC with `PS_CHECKOUT_TICKET_HMAC_KEY`; fields `{mandate_id, proposal_hash, op:"create_order", amount_minor, currency, nonce, exp}`), per agent-and-mcp s3. Adapter verifies and consumes nonce.
5. adapter `create_order` {idempotency_key=`create_request_id`, ticket, `amount_minor`, `currency`, `custom_id`, `invoice_id`, `return_url`, `cancel_url`}. return_url = `{PS_CHECKOUT_RETURN_BASE_URL}/checkout/return?state=<state>`; cancel_url = `.../checkout/cancel?state=<cancel_state>` (PayPal appends `token`, `PayerID`). URLs built from config only.
6. Success -> CAS to AWAITING_APPROVAL, save `paypal_order_id`, `approve_url` (payer action link from PayPal), outbox `order.created`, store idempotent response, 201.
7. Failure -> CREATE_FAILED (definite 4xx) or CREATE_UNKNOWN (timeout/409/UNKNOWN); response 502/503 with order_id so the client can poll.

## 6. SPIKE-VERIFIED PayPal behaviors and exactly how checkout uses them
All PayPal calls go through paypal-adapter; checkout never sees credentials.

| Verified fact (V) | Use in checkout |
|---|---|
| Same `PayPal-Request-Id` replay on order create returns the SAME order | `create_request_id` persisted before first call; any retry/reconcile reuses it; one order per `order_id` |
| Order starts `PAYER_ACTION_REQUIRED`; buyer must approve on PayPal sandbox page (real click) | Store AWAITING_APPROVAL; UI opens `approve_url`; checkout never "auto-approves" |
| After approval status `APPROVED`; capture returns 201 `COMPLETED` | Return handler requires APPROVED from our own re-fetch; only COMPLETED creates `captures` row and fires `order.captured` |
| `custom_id` and `invoice_id` on the purchase unit survive onto the capture | Pre-capture and post-capture check: `custom_id == mandate_id` and `invoice_id == order_id`, else CAPTURE_FAILED `BINDING_MISMATCH` and HUMAN follow-up; this is the trace key resolution later uses |
| `invoice_id` reuse -> 422 `DUPLICATE_INVOICE_ID` (refund spike; same field) | `invoice_id = order_id` is unique per order; a duplicate error on create is treated as a bug signal, not retried with a new id |
| OAuth token ~9 h, 401 on invalid | Adapter's concern; checkout treats adapter `REJECTED/AUTH` as retryable once |
| India-based buyer cannot pay USD; US personal buyer works | Deployment/demo note only |

NOT verified (I), handled defensively:
- Capture `PENDING` status: see s7. Never assume COMPLETED without reading it.
- Capture `PayPal-Request-Id` replay (spike covered order create and refund only): reconcile reads `get_order`/`get_capture` BEFORE any second capture call; if the order is already COMPLETED, adopt its capture instead of calling capture again.
- Order expiry window for abandoned PAYER_ACTION_REQUIRED/APPROVED orders: unknown; our `EXPIRED` uses config TTL independent of PayPal.
- `GET` order exact fields (amount/payee/custom_id presence) used by the re-fetch: adapter DTO must expose them; confirm in week 1.

## 7. Return-URL flow
Verified vs untested:
- V: sandbox redirect to `return_url` carries `token` (= PayPal order id) and `PayerID`.
- I (UNTESTED): our own server receiving that redirect, through Render + Vercel, with cookies, after a cold start. Week-1 spike item; until done the manual fallback is `POST /orders/{id}/capture` (same checks).
- I: whether PayPal appends additional query params, retains our `state` verbatim, or alters encoding. Test.

Handler `POST /orders/return` (gateway route `/orders/paypal/return`; see s12) body `{state, token, payer_id}`:
1. Hash `state` -> load binding; reject (400 `STATE_INVALID`) if absent, expired, `kind != return`, or `used_at` set (second use returns existing order result with 200 if same order, else 409).
2. Principal buyer_id must equal binding buyer_id; no principal (cookie lost) -> 401 `SIGN_IN_REQUIRED`, state NOT consumed, no capture.
3. `token` must equal stored `paypal_order_id`; otherwise 400 `TOKEN_MISMATCH` (client-supplied order identity ignored). `payer_id` stored opaque, never trusted.
4. Mandate sync check (get mandate state): revoked/expired -> CANCELLED_REVOKED, no capture.
5. Atomically mark `used_at` (UPDATE ... WHERE used_at IS NULL).
6. adapter `get_order` -> require status APPROVED; compare amount (minor), currency, `custom_id`, `invoice_id`, payee/merchant vs DB (and payee vs `merchant_settlement_map` if exposed; I). Status still PAYER_ACTION_REQUIRED -> 409 `NOT_APPROVED` (state un-consumed so buyer can retry; implement by clearing `used_at` in same txn). Mismatch -> CAPTURE_FAILED `ORDER_MISMATCH`, alert.
7. CAS AWAITING_APPROVAL -> APPROVED -> CAPTURING; persist `capture_request_id`.
8. Mint ticket (op=`capture_order`), adapter `capture_order`. COMPLETED -> s8. PENDING -> CAPTURE_PENDING (s9). Error/unknown -> s10.
9. Response is the order + receipt link (or status explanation). Log with query string stripped; `Referrer-Policy: no-referrer` enforced at gateway.
- Capture is idempotent at checkout: unique(captures.order_id) and CAS mean a double return or refresh yields the existing result.
- Cancel: `POST /orders/cancel {state}` -> CANCELLED_BUYER (P2).

## 8. Capture success
In one transaction: insert `captures`, CAS order -> CAPTURED, build and insert `receipts`, outbox `order.captured` {order_id, capture_id, mandate_id, buyer_id, merchant_ids, amount_minor, currency, captured_at, protection_window_days, mandate_hash}. Post-capture assertion repeats `custom_id`/`invoice_id`/amount check; mismatch flags the order for human review (the capture cannot be undone here).

## 9. PENDING capture (UNVERIFIED, I)
- If adapter reports capture status PENDING (or any non-COMPLETED non-error status): order -> CAPTURE_PENDING; no `captures` COMPLETED semantics, no receipt "Protected", no `order.captured`.
- Poll via reconcile `get_capture` (backoff, bounded attempts per config); on COMPLETED proceed as s8; on DECLINED/FAILED/VOIDED -> CAPTURE_FAILED with `pending_resolved_failed`; on no resolution after bound -> stays CAPTURE_PENDING and surfaced to reviewer; refunds cannot start for it (resolution reads capture status).
- UI text: "Payment is pending; protection starts when it completes." No claim of payment success.
- Test only with a fake adapter until the sandbox is seen to return PENDING.

## 10. Failure modes and reconciliation
| Failure | Behavior |
|---|---|
| catalog/mandate/evaluate down | BLOCK, 503-ish reasons in cart, no order (fail closed) |
| intent-fit down/timeout/bad JSON | NEEDS_BUYER_CONFIRMATION; never blocks nor allows |
| adapter down before create | CREATE_FAILED if connection refused before send; else CREATE_UNKNOWN; cart stays CONFIRMED-able only via idempotent replay |
| create timeout | CREATE_UNKNOWN; reconcile calls create with SAME request id (V replay) |
| PayPal 409 (concurrent same Request-Id, V for refunds) on any write | treat as in-progress -> UNKNOWN state; reconcile by GET, no new id |
| capture timeout | CAPTURE_UNKNOWN; reconcile: `get_order` (status COMPLETED -> adopt capture_id from order; APPROVED -> recapture with SAME capture_request_id once; other -> FAILED) |
| capture 422/4xx definite | CAPTURE_FAILED, `failure_code` from adapter, emit `order.capture_failed` |
| return after TTL / unknown state | 400, no state change |
| duplicate return | idempotent, existing result |
| outbox delivery failure | relay retries; money path never waits on audit |
| mandate.revoked event delayed/lost | no effect on safety: use-time sync check is authoritative |
| process restart mid-flow | all steps resumable from `orders.status`; reconcile job picks up |
| kill switch `MONEY_ENABLED=false` | adapter refuses; checkout maps to CAPTURE_FAILED/`MONEY_DISABLED` without retry loop (refund freeze is resolution's) |

Reconciler (`POST /internal/reconcile`, service/system token or scheduled): for each non-terminal order older than a grace interval (config): CREATE_UNKNOWN, CREATING, AWAITING_APPROVAL (expire), APPROVED stuck, CAPTURING, CAPTURE_UNKNOWN, CAPTURE_PENDING. Idempotent, rate-bounded (avoid Render "high outbound traffic" suspension, V).

## 11. Receipt (built at capture, served by `GET /orders/{id}/receipt`)
| Field | Source / rule |
|---|---|
| `order_id`, `paypal_order_id`, `capture_id`, `status` | our DB |
| `amount_minor`, `currency`, `lines[]` | server-derived; never client |
| `checks[]` | `cart_checks` rows at CONFIRM phase: `{name, result, reason_code, source, detail}`; includes hard checks and intent-fit |
| `intent_fit` | `{verdict, reason_code, confidence, advisory: true, note: "Advisory AI check; can only tighten; cannot clear a block"}` |
| `mandate_id`, `mandate_hash` | from mandate at confirm; also the PayPal `custom_id` |
| `audit` | `{event_id, seq}`: `event_id` known at capture; `seq` is filled by the BFF from audit `GET /entries` (checkout does not call audit; null until delivered; s12) |
| `remaining_cap_minor` | `mandate.max_total_minor - committed_minor_after_capture` (I: cumulative cap) |
| `protection` | `{window_days, protected_until_day, label: "Demo window, not PayPal's"}` |
| `disclosures[]` | `["Sandbox only", "Demo protection window is illustrative", "Merchant-funded via PayPal refund"]` |

"Protected until day X": `window_days` = deliver-by/protection days from mandate `terms` (mandate owns the number; no default invented here). Checkout stores `captured_at` (real) and `window_days`; `protected_until_day = window_days` counted from purchase day 0; the UI renders it against the demo clock (tracking owns time, so checkout does NOT call tracking: avoids an upward sync call). Resolution extends the window during open cases (threat-model s7, resolution's job).

## 12. Conflicts with other docs (service-map and ADR win) and open decisions
| # | Conflict / gap | Resolution |
|---|---|---|
| C1 | auth-gateway/threat-model call this service "orchestrator" and list `/orders`, `/orders/paypal/return` (GET) | Follow service-map names: `checkout`; public paths are gateway aliases. `POST /orders` -> `POST /carts/{id}/confirm`. Return: gateway exposes `/orders/paypal/return`; the web return page calls it as POST with `{state, token, payer_id}` (a state-changing action should not be a GET); gateway forwards to checkout `POST /orders/return`. This is an ADDITIVE endpoint beyond service-map's list; gateway doc owner to align |
| C2 | auth-gateway says `return_bindings` live at gateway/orchestrator | Owned by `checkout` (it owns order state); gateway only forwards |
| C3 | auth-gateway s3.1 says static `trusted_issuers`, no JWKS fetch; ADR-006 says cached JWKS | Follow ADR-006 (JWKS cached). Checkout verifier is a `libs/common` function; works with either |
| C4 | service-map: adapter "requires caller-supplied request_id"; agent-and-mcp adds `authorization_ticket` | Both. Checkout supplies request id and a ticket (key `PS_CHECKOUT_TICKET_HMAC_KEY`). If the adapter owner prefers callback validation, checkout provides `GET /internal/tickets/{nonce}` (decision open) |
| C5 | Receipt needs "audit seq" but dependency graph gives checkout no audit call | Receipt carries `audit.event_id`; `seq` populated by gateway BFF (gateway may read audit). No new sync edge |
| C6 | "Protected until day X" needs a clock; tracking owns time and calls checkout (not reverse) | Day offset stored by checkout; UI/demo-clock resolve date |
| C7 | overview F3 says return calls `/orders/{id}/capture`; auth-gateway says capture after return checks | Return handler performs verified capture itself; `POST /orders/{id}/capture` kept as idempotent retry/reconcile entry, same checks |
| C8 | threat-model says audit down blocks refunds; service-map says money path does not block on audit | Follow service-map for checkout: capture never waits on audit |
| C9 | service-map `GET /orders?mandate_id=` only | Add optional `status`/`buyer` scoping by role (additive); merchant read is minimal-field |
| C10 | Mandate `evaluate` described as pure with "prices in the request"; cap accumulation not specified | Checkout passes `committed_minor`. Mandate owner must accept this field or checkout enforces cumulative cap itself as a `checkout`-source check (fallback) |
| C11 | Revoke: auth-gateway says "void order"; no void API verified | Do not capture; leave order to expire; CANCELLED_REVOKED |
| C12 | agent-and-mcp mentions single `ai-service`; service-map has `shopping-agent` | Config `PS_CHECKOUT_SHOPPING_AGENT_BASE_URL`; works for either |
| C13 | Cap includes "fees" (brief) but no fee source defined | Fees only if catalog returns them; otherwise 0. I |

## 13. Idempotency summary
| Layer | Key | Persisted where | Behavior |
|---|---|---|---|
| Public mutating calls | `Idempotency-Key` header | `idempotency_keys` | same body replays response; different body 422 `IDEMPOTENCY_KEY_REUSED` |
| PayPal create | `create_request_id` | `orders` | reused on every retry (V) |
| PayPal capture | `capture_request_id` | `orders` | reused only after reconcile read; replay semantics unverified (I) |
| Order from cart | unique(`orders.cart_id`) | DB | second confirm returns same order |
| Capture | unique(`captures.order_id`) | DB | second capture impossible |
| Return `state` | single-use `used_at` | `return_bindings` | replay returns existing result |
| Events | `event_id` | `outbox`/`inbox` | consumers dedupe |

## 14. Config / env names (values only in platform env; none here)
`PS_CHECKOUT_DATABASE_URL`, `PS_CHECKOUT_DB_POOL_SIZE`, `PS_CHECKOUT_INTERNAL_JWKS_URL`, `PS_CHECKOUT_INTERNAL_JWT_AUDIENCE` (= checkout), `PS_CHECKOUT_SERVICE_SIGNING_KEY`, `PS_CHECKOUT_SERVICE_SIGNING_KID`, `PS_CHECKOUT_CATALOG_BASE_URL`, `PS_CHECKOUT_MANDATE_BASE_URL`, `PS_CHECKOUT_SHOPPING_AGENT_BASE_URL`, `PS_CHECKOUT_PAYPAL_ADAPTER_BASE_URL`, `PS_CHECKOUT_AUDIT_BASE_URL` (outbox target), `PS_CHECKOUT_TICKET_HMAC_KEY`, `PS_CHECKOUT_RETURN_BASE_URL`, `PS_CHECKOUT_RETURN_STATE_TTL_SECONDS`, `PS_CHECKOUT_ORDER_APPROVAL_TTL_SECONDS`, `PS_CHECKOUT_CURRENCY` (USD), `PS_CHECKOUT_HTTP_TIMEOUT_CATALOG_MS`, `PS_CHECKOUT_HTTP_TIMEOUT_MANDATE_MS`, `PS_CHECKOUT_HTTP_TIMEOUT_INTENT_FIT_MS`, `PS_CHECKOUT_HTTP_TIMEOUT_ADAPTER_MS`, `PS_CHECKOUT_RECONCILE_GRACE_SECONDS`, `PS_CHECKOUT_PENDING_POLL_MAX_ATTEMPTS`, `PS_CHECKOUT_OUTBOX_FLUSH_INTERVAL_SECONDS`, `INTERNAL_TICK_SECRET` (deliberately unprefixed, shared cron-trigger name across services, see mandate spec sec 13), `PS_CHECKOUT_INPROCESS_TRANSPORT` (Profile B toggle), `PS_CHECKOUT_LOG_LEVEL`. Forbidden in this service (CI env-manifest test): `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `LLM_API_KEY`, `MANDATE_HMAC_KEY`, `APPROVAL_KEY`. Defaults and numeric values are set at implementation; none are specified here.

## 15. Observability
- JSON logs: `service=checkout`, `trace_id`, `request_id`, `order_id`, `cart_id`, `status_from/to`, stable error codes. Redact `token`, `PayerID`, `state`, Authorization, Cookie.
- Metrics (log-derived, no APM): counts by cart status, block reason, order transition, capture outcome; reconcile outcomes.
- Audit-bound events carry `trace_id`; PayPal `debug_id` logged if adapter returns it (I).
