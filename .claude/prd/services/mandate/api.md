# mandate: API

Labels V/VC/I. Machine-readable truth: FastAPI-generated OpenAPI 3.1 committed at `contracts/openapi/mandate.json`; events at `contracts/events/mandate.*.v1.json`; CI fails on drift (ADR-008). This file is the human summary. Semantics live in `spec.md`. Amount values in examples are illustrative, not defaults.

## 1. Conventions
- Callers: api-gateway (user-originated; internal JWT `aud=mandate`, `act.role` buyer|merchant|reviewer, `scope` list) and services (`sub=svc:*`). The browser never calls mandate directly. Deny by default: missing/invalid token 401; role or service not in the endpoint's allow-list 403.
- Roles: B = buyer (owner only; `buyer_id` from the token), M = merchant (shared demo login; minimal view), O = reviewer, S = service caller (named), SYS = cron/system (`INTERNAL_TICK_SECRET` or `svc:poller`).
- Headers: `Authorization: Bearer <internal JWT>`, `X-Request-Id`, `traceparent`, `Content-Type: application/json`, `Idempotency-Key` (required where marked). Responses: `Cache-Control: no-store`.
- Bodies `extra=forbid`. Money = integer minor units, `currency` `USD`. Floats rejected. Client-sent `buyer_id`, `status`, `spent_minor`, `mandate_hash`, `hmac`, `mandate_id`, `created_at` -> 422 `FIELD_NOT_ALLOWED`.
- Wrong owner = 404 `MANDATE_NOT_FOUND` (no existence oracle).
- Gateway exposure (api-gateway spec sec 5): `preview`, `POST /mandates`, `GET /mandates`, `GET /mandates/{id}`, `GET /mandates/{id}/terms`, `POST .../revoke`, `GET .../verify` (new routes to add). Never exposed: `evaluate`, `summary`, reservations, grants, `/internal/*`.

## 2. Endpoints
| Method, path | Roles | Idempotency | Events | Purpose |
|---|---|---|---|---|
| POST `/mandates/preview` | B | none (each call issues a new nonce) | none | Normalize terms, render plain text, return `screen_text_hash` + nonce bound to the terms digest |
| POST `/mandates` | B | `Idempotency-Key` required | `mandate.signed` | Sign: verify text hash + nonce, hash, HMAC, store |
| GET `/mandates` | B (own) | read | none | List own mandates (BFF `buyer-home`; additive, api-gateway C9) |
| GET `/mandates/{id}` | B (owner), O, M (minimal), S | read | `mandate.expired` (once, lazily) | Mandate + derived status + spend summary |
| GET `/mandates/{id}/terms` | B, O, M, S (checkout, resolution, shopping-agent) | read | none | Protection terms + `terms_hash` + integrity; works for revoked/expired |
| GET `/mandates/{id}/summary` | S (shopping-agent, checkout) | read | none | Trusted numeric summary for agent prompts and receipts |
| GET `/mandates/{id}/verify` | B (owner), O, S | read | `mandate.integrity_failed` (once) | Re-check integrity; return hashes for comparison with the audit chain |
| POST `/mandates/{id}/revoke` | B (owner) | idempotent by state; `Idempotency-Key` optional | `mandate.revoked` (first revoke only) | Stop wins |
| POST `/mandates/{id}/evaluate` | S (checkout) | pure, no writes | none | Hard blocks vs advisory flags |
| POST `/mandates/{id}/reservations` | S (checkout) | natural key `(mandate_id, order_id)` | none | Reserve cap under row lock |
| GET `/reservations/{rid}` | S (checkout) | read | none | Reconcile |
| POST `/reservations/{rid}/authorize-capture` | S (checkout) | by state | none | Point of no return |
| POST `/reservations/{rid}/mark-unknown` | S (checkout) | by state | none | Capture outcome ambiguous |
| POST `/reservations/{rid}/commit` | S (checkout) | by state | `mandate.spend_committed`, `mandate.protection_granted` | Money captured: spent += amount, create grant |
| POST `/reservations/{rid}/release` | S (checkout) | by state | none | Give the cap back |
| GET `/grants?order_id=` , GET `/grants/{grant_id}` | S (resolution, checkout), B (own) | read | none | Per-order protection snapshot |
| POST `/internal/sweep` | SYS | idempotent | `mandate.expired` | Emit expiries, release stale RESERVED |
| GET `/internal/outbox?after=seq` | S | read | none | Pull catch-up |
| POST `/internal/outbox/flush` | SYS | idempotent | relays | Relay now (cron-safe) |
| GET `/healthz`, `/readyz` | none / SYS | read | none | Liveness; DB + keys + migration head |
`/internal/*` is never routed by the gateway (404 externally). Mandate consumes no events (service-map).

## 3. Error model and codes
Body: `{"error":{"code":"STABLE_CODE","message":"human text","details":{}},"request_id":"..."}`.
| HTTP | Codes |
|---|---|
| 400 | `VALIDATION_ERROR` (details.field path, never the offending text) |
| 401 | `UNAUTHENTICATED` |
| 403 | `ROLE_NOT_ALLOWED`, `CALLER_NOT_ALLOWED` |
| 404 | `MANDATE_NOT_FOUND` (also wrong owner), `RESERVATION_NOT_FOUND`, `GRANT_NOT_FOUND` |
| 409 | `NONCE_INVALID`, `IDEMPOTENCY_KEY_REUSED`, `POLICY_VERSION_MISMATCH`, `RESERVATION_REFUSED` (+ `hard_blocks`), `RESERVATION_CONFLICT`, `RESERVATION_EXPIRED`, `INVALID_RESERVATION_STATE`, `AMOUNT_MISMATCH`, `MANDATE_REVOKED`, `MANDATE_EXPIRED`, `MANDATE_EXHAUSTED`, `MANDATE_INTEGRITY_FAILED` |
| 422 | `FIELD_NOT_ALLOWED`, `SCREEN_TEXT_MISMATCH`, `TERMS_OUT_OF_BOUNDS`, `UNSUPPORTED_CURRENCY`, `MALFORMED_CART` |
| 429 | `RATE_LIMITED` (gateway-level; Retry-After) |
| 500 | `INTERNAL` (no details) |
| 503 | `NOT_READY` (keys/DB), `LOCK_TIMEOUT` (retry idempotently), `SIGNING_DISABLED`, `DEPENDENCY_UNAVAILABLE` (own DB only) |
An `evaluate` BLOCK is `200`, not an error. Callers treat 4xx/5xx from `evaluate` and reservation calls as BLOCK (fail closed).

## 4. POST /mandates/preview  (B)
Request (the terms the buyer is about to sign):
```json
{
  "terms": {
    "currency": "USD",
    "max_total_minor": 6000,
    "max_qty_per_line": 2,
    "merchant_allowlist": [{"merchant_id": "shop-a", "display_name": "Shop A"}],
    "intent_text": "birthday gift for a runner",
    "expires_at": "2026-11-01T12:00:00Z",
    "protection": {"kinds_covered": ["LATE", "LOST"], "max_refund_minor": 5000, "deliver_by_days": 7},
    "policy_version": "optional echo",
    "revoke_effect": "FUTURE_ONLY"
  }
}
```
Response 200:
```json
{
  "normalized_terms": {"...": "same shape with defaults materialized, NFC, sorted"},
  "screen_text": "DEMO MANDATE - sandbox only ... (render.v1 text)",
  "screen_text_hash": "<sha256-hex>",
  "render_version": "render.v1",
  "policy_version": "<current>",
  "nonce": "<base64url, shown once>",
  "nonce_expires_at": "2026-10-20T10:02:00Z"
}
```
Codes: 200, 400, 401, 403, 422 (`TERMS_OUT_OF_BOUNDS`, `UNSUPPORTED_CURRENCY`, `FIELD_NOT_ALLOWED`), 429. Side effect: one `nonces` row (hash only). Rate-limited at the gateway (sensitive route class).

## 5. POST /mandates  (B, `Idempotency-Key` required)
Request:
```json
{"terms": {"...": "exactly the preview input"}, "screen_text_hash": "<sha256-hex echoed from preview>", "nonce": "<from preview>"}
```
Server steps: idempotency lookup -> validate/normalize -> re-render and compare `screen_text_hash` -> verify nonce row (buyer, purpose, unexpired, `terms_digest`) -> in ONE transaction: insert mandate + `mandate_spend` + `nonce_uses` + `idempotency_keys` + outbox `mandate.signed`.
Response 201 (replay of the same key+body: 201 body + `Idempotent-Replay: true`):
```json
{
  "mandate_id": "uuid", "buyer_id": "uuid", "status": "active", "integrity": "OK",
  "schema": "mandate.v1", "render_version": "render.v1", "policy_version": "<pinned>",
  "currency": "USD", "max_total_minor": 6000, "max_qty_per_line": 2,
  "merchant_allowlist": [{"merchant_id": "shop-a", "display_name": "Shop A"}],
  "intent_text": "birthday gift for a runner", "expires_at": "2026-11-01T12:00:00Z",
  "protection": {"kinds_covered": ["LATE", "LOST"], "max_refund_minor": 5000, "deliver_by_days": 7},
  "revoke_effect": "FUTURE_ONLY",
  "mandate_hash": "<sha256-hex>", "screen_text_hash": "<sha256-hex>", "hmac_key_id": "<id>",
  "spent_minor": 0, "reserved_minor": 0, "remaining_minor": 6000,
  "created_at": "2026-10-20T10:00:30Z"
}
```
Codes: 201, 400, 401, 403, 409 (`NONCE_INVALID`, `IDEMPOTENCY_KEY_REUSED`, `POLICY_VERSION_MISMATCH`), 422 (`SCREEN_TEXT_MISMATCH`, `TERMS_OUT_OF_BOUNDS`, `FIELD_NOT_ALLOWED`), 429, 503 (`SIGNING_DISABLED`, `NOT_READY`).
Event: `mandate.signed` (outbox, same transaction).

## 6. GET /mandates/{id}  and  GET /mandates
- Owner (B) and O: full body as in sec 5 plus live `status` (`active|exhausted|revoked|expired`), `revoked_at?`, spend summary. `integrity:"FAILED"` -> `status:"INVALID"` and terms omitted except ids and hashes.
- M (merchant): minimal `{mandate_id, status, currency, expires_at, protection{kinds_covered,max_refund_minor,deliver_by_days}, merchant_ids}`; no `intent_text`, no `buyer_id`, no spend figures.
- S: same as owner view for `shopping-agent` and `checkout`; response never includes the raw HMAC.
- `GET /mandates?limit=` (B): own mandates, newest first, cursor-paginated; items use the owner view without `intent_text` truncation. Never lists others' (IDOR test T10).
Lazy expiry: first read after `expires_at` inserts `mandate.expired` (deterministic event id) in the same request.

## 7. GET /mandates/{id}/terms  and  GET /mandates/{id}/verify
`terms` 200:
```json
{
  "mandate_id": "uuid", "mandate_hash": "<sha256-hex>", "terms_hash": "<sha256-hex>",
  "mandate_status": "revoked", "integrity": "OK",
  "protection": {"kinds_covered": ["LATE","LOST"], "max_refund_minor": 5000, "deliver_by_days": 7},
  "revoke_effect": "FUTURE_ONLY", "policy_version": "<pinned>", "currency": "USD"
}
```
Used by resolution (check #3), checkout (receipt) and shopping-agent summary. Works for revoked and expired mandates.
`verify` 200: `{"mandate_id","integrity":"OK|FAILED","checks":{"canonical_matches":true,"hash_matches":true,"hmac_valid":true,"key_known":true,"spend_row_consistent":true},"mandate_hash","screen_text_hash","hmac_key_id","audit_compare_hint":"compare mandate_hash with the mandate.signed entry in the audit chain"}`. Failure details name the failed check only, never the stored values.

## 8. POST /mandates/{id}/revoke  (B owner)
Request: `{"reason_code": "BUYER_REQUEST"}` (enum; free text not accepted).
Response 200:
```json
{"mandate_id": "uuid", "status": "revoked", "revoked_at": "2026-10-20T11:00:00Z",
 "released_reservations": 1, "revoke_effect": "FUTURE_ONLY",
 "earned_protection_unchanged": true, "message_code": "FUTURE_PURCHASES_STOPPED"}
```
- Idempotent: repeat returns the original body (`released_reservations` as of first call), no second event.
- Mandate already expired: 200 `{"status":"expired","revoked":false}` no event (spec Q4). Exhausted: records the revocation.
- Takes the mandate row lock (spec sec 7.3), inserts the revocation, releases `RESERVED` reservations, writes outbox `mandate.revoked`, in one transaction.
- `earned_protection_unchanged` reflects decision D1(a); NEEDS USER CONFIRMATION.
Codes: 200, 401, 403, 404, 429, 503 (`LOCK_TIMEOUT`).

## 9. POST /mandates/{id}/evaluate  (S: checkout)
Request:
```json
{
  "cart": {
    "currency": "USD",
    "lines": [
      {"sku": "sku-1", "qty": 1, "unit_minor": 2500, "line_minor": 2500,
       "merchant_id": "shop-a", "sku_known": true, "stated_unit_minor": 2500}
    ],
    "total_minor": 2500
  },
  "committed_minor": 0
}
```
`committed_minor` is optional and ignored (spec C2). Response 200 (BLOCK is a normal result):
```json
{
  "decision": "BLOCK",
  "hard_blocks": [
    {"code": "OVER_CAP", "details": {"total_minor": 9000, "remaining_minor": 6000}},
    {"code": "MERCHANT_NOT_ALLOWED", "details": {"merchant_ids": ["shop-z"]}}
  ],
  "advisory_flags": [{"code": "MULTI_MERCHANT"}],
  "mandate": {"mandate_id": "uuid", "mandate_hash": "<sha256-hex>", "status": "active",
              "remaining_minor": 6000, "policy_version": "<pinned>"},
  "evaluated_at": "2026-10-20T10:05:00Z"
}
```
Hard-block codes are the closed list in spec sec 6.2; ALLOW has `hard_blocks: []`. Order is fixed. Integrity failure returns only `MANDATE_INTEGRITY_FAILED`. Codes: 200, 401, 403, 404, 422 (`MALFORMED_CART`, `FIELD_NOT_ALLOWED`). No writes, no events.

## 10. Reservations (S: checkout only)
### 10.1 POST /mandates/{id}/reservations
Request: `{"order_id":"uuid","amount_minor":2500,"currency":"USD","proposal_hash":"<sha256-hex>","cart":{...same shape as evaluate...}}`.
Under the row lock: integrity, status, full evaluate on `cart`, then `spent + reserved + amount <= max`.
201 (new) / 200 (replay): `{"reservation_id":"uuid","mandate_id":"uuid","order_id":"uuid","state":"RESERVED","amount_minor":2500,"expires_at":"...","mandate":{"spent_minor":0,"reserved_minor":2500,"remaining_minor":3500}}`.
409 `RESERVATION_REFUSED` with `details.hard_blocks[]`; 409 `RESERVATION_CONFLICT` (same order, different amount); 503 `LOCK_TIMEOUT`.
### 10.2 POST /reservations/{rid}/authorize-capture
Request: `{"order_id":"uuid","amount_minor":2500}` (must match the reservation).
200: `{"reservation_id":"uuid","state":"CAPTURING","authorized_at":"..."}`. Repeat while `CAPTURING`: same 200 (does not re-check revoke; the point of no return was already crossed).
409: `MANDATE_REVOKED` | `MANDATE_EXPIRED` | `MANDATE_INTEGRITY_FAILED` | `RESERVATION_EXPIRED` | `INVALID_RESERVATION_STATE` | `AMOUNT_MISMATCH`. On the first four the reservation is released in the same transaction and checkout must NOT capture.
### 10.3 POST /reservations/{rid}/mark-unknown
Request `{"reason_code":"CAPTURE_TIMEOUT"}`; `CAPTURING -> CAPTURE_UNKNOWN`; amount stays reserved.
### 10.4 POST /reservations/{rid}/commit
Request: `{"capture_id":"<paypal capture id>","captured_amount_minor":2500,"currency":"USD","captured_at":"2026-10-20T10:07:00Z"}`.
200: `{"reservation_id":"uuid","state":"CAPTURED","grant_id":"uuid","mandate":{"spent_minor":2500,"reserved_minor":0,"remaining_minor":3500},"protection":{"kinds_covered":["LATE","LOST"],"max_refund_minor":5000,"deliver_by_days":7,"terms_hash":"<sha256-hex>"}}`.
Allowed on revoked/expired mandates when the reservation was authorized (earned protection, spec sec 8). 409 `AMOUNT_MISMATCH` (reservation unchanged), 409 `INVALID_RESERVATION_STATE`.
### 10.5 POST /reservations/{rid}/release
Request: `{"reason_code":"ORDER_FAILED|BUYER_CANCELLED|CAPTURE_NOT_PERFORMED","capture_outcome":"NOT_CAPTURED"}` (`capture_outcome` required only when state is `CAPTURING`/`CAPTURE_UNKNOWN`). 200 `{"state":"RELEASED"}`; 409 `INVALID_RESERVATION_STATE` (e.g. already `CAPTURED`).
### 10.6 GET /reservations/{rid}
200 with state, amounts, timestamps, `capture_id?`. Used by checkout's reconcile job.

## 11. GET /grants
`GET /grants?order_id=<uuid>` -> 200:
```json
{
  "grant_id": "uuid", "mandate_id": "uuid", "order_id": "uuid", "capture_id": "<paypal capture id>",
  "buyer_id": "uuid", "mandate_hash": "<sha256-hex>", "terms_hash": "<sha256-hex>",
  "terms": {"kinds_covered": ["LATE","LOST"], "max_refund_minor": 5000, "deliver_by_days": 7,
            "currency": "USD", "revoke_effect": "FUTURE_ONLY", "policy_version": "<pinned>"},
  "captured_amount_minor": 2500, "captured_at": "2026-10-20T10:07:00Z",
  "mandate_status": "revoked", "protection_in_force": true, "integrity": "OK"
}
```
404 `GRANT_NOT_FOUND`. Buyer sees only own grants (404 otherwise). `integrity` re-verifies the grant HMAC and the mandate HMAC at read time; `FAILED` -> `protection_in_force:false` and resolution routes to HUMAN_REVIEW (`TERMS_INVALID`).

## 12. Internal and health
- `POST /internal/sweep` -> `{"expired_emitted":0,"reservations_released":0,"stuck_capture_alerts":0}`; safe to repeat; callable by the in-process loop and by a scheduled external call (Render cron is not free; GitHub Actions schedule or free pinger).
- `GET /internal/outbox?after=seq` -> events after `seq` (pull catch-up when a consumer wakes); `POST /internal/outbox/flush` -> `{"delivered":0,"pending":0}`.
- `GET /healthz` -> 200 `{"status":"ok"}` (no DB). `GET /readyz` -> 200 or 503 `{"db":"ok","keys":"ok","migration_head":"ok","trusted_issuers":"ok"}`; missing/short key or migration behind head = 503 (fail closed). No secrets or key ids with secret material in the body.

## 13. Events (full list in spec sec 11)
| Event | Trigger | Consumers |
|---|---|---|
| `mandate.signed` | `POST /mandates` success | audit |
| `mandate.revoked` | first revoke | audit, checkout, resolution |
| `mandate.expired` | first read after expiry / sweeper | audit |
| `mandate.spend_committed` | commit | audit |
| `mandate.protection_granted` | commit | audit, resolution |
| `mandate.integrity_failed` | first failed verification | audit |
Delivery: transactional outbox, HTTP push to `POST /internal/events` of subscribers (audit uses `POST /append`), at-least-once, dedupe by `event_id`. Consumers must never rely on events for authorization: checkout and resolution re-read mandate state synchronously at use time (an event lag cannot allow spend).

## 14. Contract notes for neighbors (additive; see spec sec 12)
- checkout: call reserve at confirm, authorize-capture immediately before the adapter capture, commit after capture COMPLETED, release on definite failure; treat any non-2xx from these as no-capture; stop sending `committed_minor`.
- resolution: read `GET /grants?order_id=` at case open and again at refund check #3; do not cancel offers inside a grant on `mandate.revoked` (needs D1 confirmation).
- api-gateway: add routes for `preview`, `verify`, list; keep `evaluate`, `summary`, reservations, grants, `/internal/*` unexposed.
- audit: accept `mandate.spend_committed`, `mandate.protection_granted`, `mandate.integrity_failed`.
