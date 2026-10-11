# checkout: API

Labels V/VC/I. Machine-readable truth: FastAPI-generated OpenAPI 3.1 committed at `contracts/openapi/checkout.json`; events at `contracts/events/*.v1.json`; CI fails on drift (ADR-008). This file is the human summary.

## 1. Conventions
- Callers: api-gateway (user-originated, internal JWT `aud=checkout`, `act.role` buyer|merchant) and services (`svc:*`). Browser never calls checkout directly.
- Headers: `Authorization: Bearer <internal JWT>`, `X-Request-Id`, `traceparent`, `Idempotency-Key` (required on POST that mutates), `Content-Type: application/json`.
- All bodies `extra=forbid`. Money = integer minor units, `currency` `USD`. Client-sent `amount`, `currency`, `merchant`, `capture_id` are rejected with 422 `FIELD_NOT_ALLOWED` (not silently ignored).
- Error body: `{"error": {"code": "STABLE_CODE", "message": "human text", "details": {}}, "request_id": "..."}`.
- IDs are opaque UUIDs; ownership: buyer_id from token only; wrong owner -> 404.

## 2. Endpoints
Roles: B = buyer (owner), M = merchant (shared demo login), S = service (`svc:*`), SYS = system job.

| Method, path | Roles | Purpose |
|---|---|---|
| POST `/carts` | B | Re-price, check, advisory intent-fit |
| GET `/carts/{cart_id}` | B | Cart + checks |
| POST `/carts/{cart_id}/confirm` | B | Re-check, create order, return approve URL |
| POST `/orders/return` | B | PayPal return handling and verified capture (gateway alias `/orders/paypal/return`) |
| POST `/orders/cancel` | B | cancel_url handling (P2) |
| POST `/orders/{order_id}/capture` | B, SYS | Idempotent retry/reconcile of capture |
| GET `/orders/{order_id}` | B, M(min), S | Order + capture facts |
| GET `/orders/{order_id}/receipt` | B, S | Receipt |
| GET `/orders?mandate_id=&status=` | B(own), M(captured, min), S | List |
| POST `/internal/events` | S | Event inbox (HMAC/internal token) |
| GET `/internal/outbox?after=seq` | S | Pull catch-up |
| POST `/internal/outbox/flush` | SYS | Relay now (cron-safe) |
| POST `/internal/reconcile` | SYS | Reconcile non-terminal orders |
| GET `/healthz`, `/readyz` | none/SYS | Liveness; DB + dependency flags |

`/internal/*` is never routed by the gateway (404 externally).

## 3. POST /carts
Request
```json
{
  "mandate_id": "uuid",
  "lines": [{"sku": "RUN-SOCKS-01", "qty": 2}],
  "proposal_id": "uuid-or-null",
  "stated_unit_prices_minor": {"RUN-SOCKS-01": 1500}
}
```
- `stated_unit_prices_minor` optional, never used for money; a mismatch with catalog -> hard block `PRICE_MISMATCH`. (SKU values illustrative.)

Response 201
```json
{
  "cart_id": "uuid",
  "status": "CHECKED | NEEDS_CONFIRMATION | BLOCKED",
  "currency": "USD",
  "lines": [{"sku": "...", "qty": 2, "unit_minor": 0, "line_minor": 0, "merchant_id": "..."}],
  "total_minor": 0,
  "remaining_cap_minor_after": 0,
  "proposal_hash": "sha256-hex",
  "checks": [
    {"name": "MANDATE_ACTIVE", "result": "PASS", "reason_code": null, "source": "mandate"},
    {"name": "WITHIN_CAP", "result": "BLOCK", "reason_code": "OVER_CAP", "source": "mandate"},
    {"name": "INTENT_FIT", "result": "TIGHTEN", "reason_code": "INTENT_FIT_NEEDS_CONFIRMATION", "source": "intent_fit", "advisory": true}
  ],
  "intent_fit": {"verdict": "PASS | NEEDS_BUYER_CONFIRMATION | REJECT_WITH_REASON", "reason_code": "OK", "advisory": true},
  "expires_at": "iso8601"
}
```
Numbers above are placeholders; real values come from catalog/mandate.

Codes: 201 (including BLOCKED carts: a block is a normal result, not an error), 400 `VALIDATION_ERROR`, 401, 403 `ROLE_NOT_ALLOWED`, 404 `MANDATE_NOT_FOUND` (also wrong owner), 422 `FIELD_NOT_ALLOWED`, 422 `IDEMPOTENCY_KEY_REUSED`, 429, 503 `DEPENDENCY_UNAVAILABLE` only for checkout's own DB failure (dependency failures yield 201 + BLOCK reasons).

## 4. POST /carts/{cart_id}/confirm
Request
```json
{"proposal_hash": "sha256-hex", "confirm_intent_fit": false}
```
- `confirm_intent_fit: true` required when cart is NEEDS_CONFIRMATION.

Response 201
```json
{
  "order_id": "uuid",
  "status": "AWAITING_APPROVAL",
  "approve_url": "https://<paypal sandbox approval page>",
  "total_minor": 0,
  "currency": "USD",
  "expires_at": "iso8601"
}
```
Codes: 201; 200 on idempotent replay; 404; 409 `CART_CHANGED` (hash mismatch or re-check produced a different cart; response includes new cart); 409 `CART_ALREADY_ORDERED` (returns existing order_id); 422 `CART_BLOCKED` with `details.reasons[]`; 422 `INTENT_FIT_CONFIRMATION_REQUIRED`; 502 `PAYPAL_CREATE_FAILED`; 503 `PAYPAL_CREATE_UNKNOWN` (order_id returned; poll `GET /orders/{id}`); 429.

## 5. POST /orders/return
Request (from web return page, via gateway)
```json
{"state": "opaque", "token": "paypal-order-id", "payer_id": "opaque"}
```
Response 200
```json
{
  "order_id": "uuid",
  "status": "CAPTURED | CAPTURE_PENDING | CAPTURE_UNKNOWN | CANCELLED_REVOKED | CAPTURE_FAILED",
  "receipt_url": "/orders/{order_id}/receipt",
  "message_code": "CAPTURED | PENDING_PROTECTION_NOT_STARTED | MANDATE_REVOKED | TRY_AGAIN"
}
```
Codes: 200; 400 `STATE_INVALID`; 400 `TOKEN_MISMATCH`; 401 `SIGN_IN_REQUIRED` (state not consumed); 403 `BUYER_MISMATCH`; 409 `NOT_APPROVED` (buyer has not approved yet; state still usable); 409 `STATE_ALREADY_USED_OTHER_ORDER`; 422 `ORDER_MISMATCH` (amount/currency/custom_id/invoice_id differ; no capture); 503 `PAYPAL_UNAVAILABLE`. Re-posting a consumed state for the same order returns 200 with the current order (idempotent).

## 6. POST /orders/{order_id}/capture
- Body `{}`; `Idempotency-Key` required. Runs identical checks to s5 from current order state: re-fetch, compare, mandate check, capture. Used for the manual fallback if the redirect failed (UNTESTED return path, I) and by reconcile.
- Codes: 200 current/updated order; 404; 409 `ORDER_NOT_CAPTURABLE` (state not APPROVED/AWAITING/CAPTURE_UNKNOWN); 409 `NOT_APPROVED`; 422 `MANDATE_REVOKED` (order -> CANCELLED_REVOKED); 422 `ORDER_MISMATCH`.

## 7. GET /orders/{order_id}
```json
{
  "order_id": "uuid", "cart_id": "uuid", "mandate_id": "uuid", "buyer_id": "uuid",
  "status": "CAPTURED", "total_minor": 0, "currency": "USD",
  "paypal_order_id": "...", "invoice_id": "order uuid", "custom_id": "mandate uuid",
  "capture": {"capture_id": "...", "amount_minor": 0, "currency": "USD", "captured_at": "iso8601", "paypal_status": "COMPLETED"},
  "failure_code": null, "created_at": "iso8601"
}
```
- Merchant role: minimal fields (order_id, status, lines, capture_id, invoice_id), no buyer_id/mandate_id beyond what tracking needs (I: confirm with web).

## 8. GET /orders/{order_id}/receipt
```json
{
  "order_id": "uuid", "capture_id": "...", "status": "CAPTURED",
  "amount_minor": 0, "currency": "USD",
  "lines": [{"sku": "...", "qty": 1, "unit_minor": 0, "line_minor": 0, "merchant_id": "..."}],
  "checks": [{"name": "MERCHANT_ALLOWED", "result": "PASS", "reason_code": null, "source": "mandate"}],
  "intent_fit": {"verdict": "PASS", "reason_code": "OK", "confidence": 0.0, "advisory": true,
                 "note": "Advisory AI check; can only tighten; cannot clear a block"},
  "mandate": {"mandate_id": "uuid", "mandate_hash": "sha256-hex"},
  "audit": {"event_id": "uuid", "seq": null},
  "remaining_cap_minor": 0,
  "protection": {"window_days": 0, "protected_until_day": 0, "label": "Demo window, not PayPal's"},
  "disclosures": ["Sandbox only", "Demo protection window is illustrative", "Merchant-funded via PayPal refund"]
}
```
- `audit.seq` is null from checkout; the gateway BFF fills it from audit. Placeholders are not real values. 404 if not CAPTURED (409 `RECEIPT_NOT_READY` for pending states).

## 9. GET /orders?mandate_id=&status=
- Buyer: own orders only. Services: any. Pagination `limit` (server max in config) + `cursor`; sort `created_at desc`. Response `{"items": [Order...], "next_cursor": null}`.

## 10. Internal
- `POST /internal/events`: envelope `{event_id, type, version, occurred_at, producer, aggregate_id, trace_id, payload}`. Handles `mandate.revoked` (marks matching un-captured carts BLOCKED/SUPERSEDED, sets non-terminal pre-capture orders for re-check at next step). 200 duplicate-safe via `inbox`. 400 unknown version.
- `POST /internal/reconcile` -> `{"examined": 0, "advanced": 0, "unchanged": 0, "errors": []}`; safe to repeat.
- `GET /readyz` -> `{"db": "ok", "mandate": "ok|unreachable", "catalog": "...", "adapter": "..."}`; unreachable deps flag degraded, not crash.

## 11. Events emitted (outbox -> audit; checkout consumes `mandate.revoked`)
| Event | When | Payload (no PII, no secrets) |
|---|---|---|
| `cart.checked` | after `POST /carts` and after confirm re-check | cart_id, mandate_id, status, total_minor, currency, proposal_hash, reason_codes[], intent_fit_verdict, advisory:true |
| `order.created` | after PayPal order created | order_id, cart_id, mandate_id, paypal_order_id, total_minor, currency, custom_id, invoice_id |
| `order.captured` | only on PayPal COMPLETED | order_id, capture_id, mandate_id, buyer_id, merchant_ids, amount_minor, currency, captured_at, protection_window_days, mandate_hash. Consumers: audit, tracking |
| `order.capture_failed` | definite failure or revoked pre-capture | order_id, mandate_id, reason (MANDATE_REVOKED, ORDER_MISMATCH, BINDING_MISMATCH, PAYPAL_DECLINED, MONEY_DISABLED, PENDING_UNRESOLVED), final_status |
Delivery at-least-once; consumers dedupe by `event_id`. Additive-only changes within `v1`.

## 12. Authorization matrix (summary)
| Endpoint | buyer | merchant | svc | anon |
|---|---|---|---|---|
| POST /carts, /confirm, /orders/return, /orders/cancel | own | no | no | no |
| GET order/receipt | own | min (order only) | yes | no |
| POST /orders/{id}/capture | own | no | SYS | no |
| /internal/* | no | no | yes | no |
Return endpoint is authenticated (buyer) AND state-bound; PayPal is never a principal.

## 13. Rate limits (gateway-enforced; starting values in auth-gateway s2.4, I) and size limits
- Body max bytes and line count per config; no numeric defaults asserted here.
