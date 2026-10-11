# paypal-adapter: API (internal REST + MCP tools)

Date: 2026-10-10. Labels: V verified (our sandbox spike 2026-10-10), VC vendor claim, I inference/unverified. Source of truth: `spec.md` (sections 3, 5, 6, 7, 13). service-map.md and adr.md win on conflict (spec section 14 lists them). Python 3.12, FastAPI, Pydantic v2 `extra="forbid"`. No credentials appear here; all example values are fake placeholders.

## 1. Conventions
- Base: internal only. Never routed by `api-gateway` (gateway returns 404 for `/internal/*`, has no route to the adapter).
- Auth on every call: `Authorization: Bearer <internal service JWT>`; EdDSA pinned, `aud=paypal-adapter`, short exp, caller = JWT `sub` (`checkout`, `tracking`, `resolution`). Caller identity is never read from body or headers.
- Money tools additionally need `X-Authorization-Ticket: <ticket>` (REST) or the `authorization_ticket` string argument (MCP). Ticket format and the 9-step verification order: spec section 5.
- `request_id`: UUID, caller-generated and persisted BEFORE the call (ADR-011); sent to PayPal unchanged as `PayPal-Request-Id` (C3: `request_id`, not `idempotency_key`). Missing = 422 `REQUEST_ID_REQUIRED`.
- Amounts: integer minor units (`amount_minor`) + `currency` (USD only in demo). Converted to a PayPal decimal string inside the adapter; no floats (S24).
- Trace: `X-Trace-Id` in, echoed as `trace_id`.
- IDs (path/body): regex `^[A-Za-z0-9_-]{1,64}$`; anything else is `VALIDATION_ERROR` before any outbound call.
- Unknown JSON fields are rejected (`extra="forbid"`).

## 2. Response envelope (REST and MCP, one shape)
```json
{
  "ok": true,
  "status": "OK",
  "paypal_http_status": 201,
  "data": { },
  "error": null,
  "replayed": false,
  "trace_id": "tr_01"
}
```
- `status`: `OK | IN_PROGRESS | REJECTED | UNKNOWN`.
- `error` (when `ok=false`): `{ "code": "...", "message": "<fixed text>", "retryable": false, "paypal_name": "<truncated PayPal name or null>" }`. PayPal message bodies are never forwarded.
- HTTP mapping: OK 200/201; IN_PROGRESS 202; REJECTED 400/403/404/409/422 by code; UNKNOWN 504; read upstream down 502/503; inbound rate limit 429 + `Retry-After`; `UPSTREAM_AUTH_FAILED` 503.
- MCP: same envelope in `structuredContent` + a short text; `isError=true` when `ok=false`.

## 3. Caller allowlist matrix (server-enforced before dispatch; default compiled in, override `PS_PAYPALADAPTER_CALLER_ALLOWLIST_JSON`)
| Tool | Class | Ticket | checkout | tracking | resolution | demo-inspector (off by default) | shopping-agent, triage-ai, api-gateway, web, mandate, catalog, audit |
|---|---|---|---|---|---|---|---|
| create_order | MONEY | yes | allow | - | - | - | - |
| capture_order | MONEY | yes | allow | - | - | - | - |
| refund_capture | MONEY | yes | - | - | allow | - | - |
| get_order | READ | no | allow | allow | allow | allow | - |
| get_capture | READ | no | allow | allow | allow | allow | - |
| get_refund | READ | no | - | - | allow | allow | - |
| add_tracking | WRITE | no | - | allow | - | - | - |
| get_tracking | READ | no | - | allow | allow | allow | - |
- Denied pair: HTTP 403, code `NOT_PERMITTED`, audited (`paypal.call_denied`, or `paypal.call_recorded` with `status=DENIED` if the event addition is rejected, spec C10).
- Least-privilege notes: `checkout` has no tracking/refund tools (C5: service-map line 74 says checkout tracks; allowlist follows the dependency graph, `tracking` owns add_tracking). Ticket minters are separate: checkout key mints create_order/capture_order only; resolution key mints refund_capture only.
- MCP `tools/list` is filtered per caller; `tools/call` re-checks. LLM-facing services get no JWT scope and no minting key.
- `refund_capture` is a deprecated alias for `refund_capture` in code (ADR-007/service-map name), not listed in `tools/list` (C2).

## 4. REST endpoints
All under `/v1`. Health endpoints are unauthenticated and carry no secrets.

| Method + path | Tool | Class | PayPal call (V unless noted) |
|---|---|---|---|
| POST `/v1/orders` | create_order | MONEY | POST `/v2/checkout/orders` |
| GET `/v1/orders/{id}` | get_order | READ | GET `/v2/checkout/orders/{id}` |
| POST `/v1/orders/{id}/capture` | capture_order | MONEY | POST `/v2/checkout/orders/{id}/capture` |
| GET `/v1/captures/{id}` | get_capture | READ | GET `/v2/payments/captures/{id}` |
| POST `/v1/orders/{id}/track` | add_tracking | WRITE | POST `/v2/checkout/orders/{id}/track` |
| GET `/v1/orders/{id}/trackers/{tracker_id}` | get_tracking | READ | tracker GET path UNVERIFIED (I, U2) |
| POST `/v1/captures/{id}/refund` | refund_capture | MONEY | POST `/v2/payments/captures/{id}/refund` |
| GET `/v1/refunds/{id}` | get_refund | READ | GET `/v2/payments/refunds/{id}` |
| POST `/v1/reconcile/{request_id}` | (helper, COULD) | READ | get_order / get_capture / get_refund by ledger row |
| GET `/v1/control/status` | (resolution check #1) | READ | none; returns `{money_enabled, frozen}` from adapter schema (C6) |
| POST `/v1/control/freeze` , `/v1/control/unfreeze` | operator only | - | none; sets `paypal.control_flags` |
| POST `/v1/webhooks/paypal` | optional, `PS_PAYPALADAPTER_WEBHOOK_ENABLED=false` default | - | hint only (U3) |
| GET `/healthz`, `/readyz`, `/health` (alias, C8) | - | - | none |

Not exposed (deliberate): tracker PATCH (CANCELLED irreversible, V), order PATCH, void/authorize, payouts, vault, disputes.

## 5. Operations with examples

### 5.1 create_order (MONEY, ticket `op=create_order`, minter `checkout`)
Request `POST /v1/orders`, header `X-Authorization-Ticket`.
```json
{
  "request_id": "7b1e0a5e-2f0c-4a53-9b0e-000000000001",
  "mandate_id": "mdt_demo_01",
  "proposal_hash": "sha256:<hex>",
  "internal_order_id": "ord_demo_01",
  "amount_minor": 4999,
  "currency": "USD",
  "return_url": "https://<host>/api/paypal/return",
  "cancel_url": "https://<host>/api/paypal/cancel"
}
```
- Adapter sets `custom_id = ticket.mandate_id`, `invoice_id = ticket.subject (= internal_order_id)` (survive onto capture, V). `return_url`/`cancel_url` origins must be in `PS_PAYPALADAPTER_PAYPAL_RETURN_URL_ALLOWED_ORIGINS` (else `VALIDATION_ERROR`). Exact JSON placement of the URLs in the PayPal body: copy from the spike script (I until pinned in a fixture).
- 201 response:
```json
{
  "ok": true, "status": "OK", "paypal_http_status": 201,
  "data": {
    "order_id": "5O190127TN364715T",
    "status": "PAYER_ACTION_REQUIRED",
    "approve_url": "https://www.sandbox.paypal.com/checkoutnow?token=5O190127TN364715T",
    "custom_id": "mdt_demo_01", "invoice_id": "ord_demo_01",
    "amount_minor": 4999, "currency": "USD"
  },
  "error": null, "replayed": false, "trace_id": "tr_01"
}
```
- Replay with same `request_id` + same body: same order (V, S04), `replayed=true`, no new PayPal call. Same `request_id` + different body: `IDEMPOTENCY_KEY_REUSED`.
- Errors: `REQUEST_ID_REQUIRED`, `TICKET_INVALID|EXPIRED|REPLAYED`, `AUTHORIZATION_MISMATCH`, `NOT_PERMITTED`, `MONEY_FROZEN`, `AMOUNT_OVER_CEILING`, `CURRENCY_UNSUPPORTED`, `VALIDATION_ERROR`, `UPSTREAM_*`.

### 5.2 get_order (READ)
`GET /v1/orders/{id}` -> `data: { order_id, status (PAYER_ACTION_REQUIRED | APPROVED | COMPLETED | ...), custom_id, invoice_id, amount_minor, currency, capture_ids: [] }` (transitions observed, V; fields beyond these are parsed leniently, U5). 404 -> `NOT_FOUND`.

### 5.3 capture_order (MONEY, ticket `op=capture_order`, minter `checkout`)
Request `POST /v1/orders/{id}/capture`:
```json
{
  "request_id": "7b1e0a5e-2f0c-4a53-9b0e-000000000002",
  "mandate_id": "mdt_demo_01",
  "proposal_hash": "sha256:<hex>",
  "amount_minor": 4999,
  "currency": "USD"
}
```
- Adapter pre-checks via get_order: status APPROVED, `custom_id == mandate_id`, amount/currency == ticket; else `ORDER_NOT_APPROVED` / `AUTHORIZATION_MISMATCH` (PayPal's own not-approved error name is unverified, U8).
- 201 response `data: { order_id, status: "COMPLETED", capture_id, capture_status: "COMPLETED", custom_id, invoice_id, amount_minor, currency }` (V, S07).
- Timeout/5xx: `status=UNKNOWN`, `UPSTREAM_UNAVAILABLE`; caller reconciles with get_order; never recapture under a new request_id (S25).

### 5.4 get_capture (READ)
`GET /v1/captures/{id}` -> `data: { capture_id, status (COMPLETED | PARTIALLY_REFUNDED | ...), custom_id, invoice_id, amount_minor, currency, refundable_remaining_minor, refundable_remaining_source: "derived" }`. `refundable_remaining` = captured minus sum of our `refund_ledger` COMPLETED/PENDING rows, labelled `derived` (whether PayPal exposes a total, U5/C13).

### 5.5 add_tracking (WRITE, no ticket, caller `tracking`)
Request `POST /v1/orders/{id}/track`:
```json
{
  "request_id": "7b1e0a5e-2f0c-4a53-9b0e-000000000003",
  "capture_id": "3C679366HH908993F",
  "tracking_number": "PS-DEMO-0001",
  "carrier_name_other": "Demo Carrier (simulated)",
  "notify_payer": false
}
```
- Adapter always sends `carrier: "OTHER"`; never sends `status` (ignored at creation, V S10). 201 response `data: { tracker_id: "3C679366HH908993F-PS-DEMO-0001", status: "SHIPPED" }` (V S08). Multiple trackers per capture OK (S09). Duplicate (capture_id, tracking_number) returns the existing tracker with `replayed=true`. Effect of `PayPal-Request-Id` on this endpoint: I (U9); natural-key ledger is the guard.
- This is a "tracking added" signal only. PayPal cannot hold late/lost/delivered (V).

### 5.6 get_tracking (READ)
`GET /v1/orders/{id}/trackers/{tracker_id}` -> `data: { tracker_id, paypal_status, carrier_status: "SIMULATED:<state>" , verified: false }`. Path UNVERIFIED (U2): until pinned, returns derived tracker id + `verified:false`; late/lost state is merged from OUR `tracking` data and labelled `SIMULATED`.

### 5.7 refund_capture (MONEY, ticket `op=refund_capture`, minter `resolution`)
Request `POST /v1/captures/{id}/refund`:
```json
{
  "request_id": "7b1e0a5e-2f0c-4a53-9b0e-000000000004",
  "mandate_id": "mdt_demo_01",
  "proposal_hash": "sha256:<hex>",
  "amount_minor": 1500,
  "currency": "USD",
  "invoice_id": "ref_demo_01"
}
```
- `invoice_id` optional; `note_to_payer` is a static template (no model text to PayPal).
- Pre-checks: `get_capture.custom_id == mandate_id`, currency equal, `amount_minor <= PS_PAYPALADAPTER_REFUND_MAX_MINOR` and `<= derived refundable_remaining`.
- 201 response `data: { refund_id: "1JU08902781691411", status: "COMPLETED", capture_id, amount_minor: 1500, currency: "USD" }` (V S15). `status` enum `COMPLETED | PENDING | FAILED`; PENDING is unverified (U1): callers treat it as non-final and reconcile with get_refund.
- Replay same `request_id` + same body: original refund, `replayed=true`. Same `request_id` + different amount: `IDEMPOTENCY_KEY_REUSED` (OUR guard; PayPal would return the original, V S18).
- 422 over-refund -> `REFUND_AMOUNT_EXCEEDED` (V S19); 422 reused `invoice_id` -> `DUPLICATE_INVOICE_ID` (V S20). Resolution maps both to FAILED -> HUMAN_REVIEW.

### 5.8 get_refund (READ)
`GET /v1/refunds/{id}` -> `data: { refund_id, status, amount_minor, currency, capture_id }` (V S22).

## 6. 409 and IN_PROGRESS semantics
- PayPal 409 on a write (two concurrent identical refunds with the same Request-Id: one 201, one 409, V S21) -> ledger `IN_PROGRESS_REMOTE`; adapter returns:
```json
{ "ok": false, "status": "IN_PROGRESS", "paypal_http_status": 409, "data": null,
  "error": { "code": "IN_PROGRESS", "message": "Request is being processed; reconcile.", "retryable": false, "paypal_name": null },
  "replayed": false, "trace_id": "tr_02" }
```
- HTTP 202. Caller rules: NEVER blind-retry and NEVER mint a new `request_id` for the same intent; call `get_refund` / `get_capture` / `get_order` (or `POST /v1/reconcile/{request_id}`) until final. Resolution maps IN_PROGRESS/UNKNOWN to `refund_attempt = UNKNOWN`.
- Local concurrent duplicate (ledger row IN_FLIGHT) also returns `IN_PROGRESS` without calling PayPal.
- Ledger `UNKNOWN` (timeout/5xx on write) returns `UNKNOWN` again for the same `request_id` until reconciled.

## 7. Error codes (ours)
`REQUEST_ID_REQUIRED` 422; `VALIDATION_ERROR` 422; `NOT_PERMITTED` 403; `TICKET_INVALID` 403; `TICKET_EXPIRED` 403; `TICKET_REPLAYED` 409; `AUTHORIZATION_MISMATCH` 403; `MONEY_FROZEN` 403; `IDEMPOTENCY_KEY_REUSED` 409 (REJECTED); `ORDER_NOT_APPROVED` 409; `AMOUNT_OVER_CEILING` 422; `CURRENCY_UNSUPPORTED` 422; `NOT_FOUND` 404; `INVALID_PARAMETER` 400 (PayPal `INVALID_PARAMETER_VALUE`, V; we never send such calls); `REFUND_AMOUNT_EXCEEDED` 422; `DUPLICATE_INVOICE_ID` 422; `UPSTREAM_REJECTED` 422 (+`paypal_name`); `UPSTREAM_AUTH_FAILED` 503 (after one refresh + retry, V invalid token -> 401); `UPSTREAM_UNAVAILABLE` 504 write / 502-503 read; `RATE_LIMITED` (PayPal 429, I, writes treated UNKNOWN); `RATE_LIMITED_INBOUND` 429 + `Retry-After`. HTTP codes for the "ours" rows are proposed here (I) pending contract lint; envelope `code` is the contract.

## 8. MCP server (`/mcp`, streamable HTTP, ADR-007)
- Our own MCP server over verified REST calls. NOT the official `@paypal/mcp` (comparison only). Mount API and stateless mode: I (U11); fallback is a hand-written JSON-RPC handler.
- ASGI middleware verifies the JWT before the MCP app; 401 if missing/invalid. `additionalProperties:false`, string length caps, ID regexes on every input. No resources/prompts in v1.
- Every tool takes `request_id` for writes; money tools take `authorization_ticket` (opaque string, supersedes the nested object in agent-and-mcp, C7) plus the same fields the ticket binds, for comparison.

Tool input schemas (JSON Schema, abbreviated shared defs):
```json
{
  "$defs": {
    "id":  { "type": "string", "pattern": "^[A-Za-z0-9_-]{1,64}$" },
    "uuid": { "type": "string", "format": "uuid" },
    "minor": { "type": "integer", "minimum": 1 },
    "ccy": { "type": "string", "enum": ["USD"] },
    "ticket": { "type": "string", "maxLength": 2048 }
  }
}
```
| Tool | Required args (all `additionalProperties:false`) |
|---|---|
| create_order | `request_id`, `authorization_ticket`, `mandate_id` (id), `proposal_hash`, `internal_order_id` (id), `amount_minor`, `currency`, `return_url`, `cancel_url` |
| get_order | `order_id` |
| capture_order | `request_id`, `authorization_ticket`, `order_id`, `mandate_id`, `proposal_hash`, `amount_minor`, `currency` |
| get_capture | `capture_id` |
| add_tracking | `request_id`, `order_id`, `capture_id`, `tracking_number` (maxLength 64), `carrier_name_other` (maxLength 64), optional `notify_payer` (default false) |
| get_tracking | `order_id`, `tracker_id` |
| refund_capture | `request_id`, `authorization_ticket`, `capture_id`, `mandate_id`, `proposal_hash`, `amount_minor`, `currency`, optional `invoice_id` (id) |
| get_refund | `refund_id` |

Example MCP call (refund_capture) and result:
```json
{ "jsonrpc": "2.0", "id": 1, "method": "tools/call",
  "params": { "name": "refund_capture",
    "arguments": { "request_id": "7b1e0a5e-2f0c-4a53-9b0e-000000000004", "authorization_ticket": "<opaque>",
      "capture_id": "3C679366HH908993F", "mandate_id": "mdt_demo_01", "proposal_hash": "sha256:<hex>",
      "amount_minor": 1500, "currency": "USD" } } }
```
```json
{ "jsonrpc": "2.0", "id": 1, "result": { "isError": false,
  "structuredContent": { "ok": true, "status": "OK", "paypal_http_status": 201,
    "data": { "refund_id": "1JU08902781691411", "status": "COMPLETED", "capture_id": "3C679366HH908993F", "amount_minor": 1500, "currency": "USD" },
    "error": null, "replayed": false, "trace_id": "tr_03" },
  "content": [ { "type": "text", "text": "Refund COMPLETED (sandbox)." } ] } }
```
Refusal demo (read-only inspector calling a money tool): `tools/list` does not include it; a direct call returns `isError=true`, `error.code=NOT_PERMITTED`.

## 9. Events (outbox in schema `paypal`, HTTP push to audit; envelope per overview section 7; at-least-once, consumers dedupe on `event_id`)
- `paypal.call_recorded` (service-map): emitted for every outbound PayPal call.
```json
{ "event_id": "evt_01", "type": "paypal.call_recorded", "version": 1, "ts": "<iso>", "trace_id": "tr_01",
  "payload": { "tool": "refund_capture", "caller": "resolution", "request_id_hash": "sha256:<hex>", "ticket_tid": "<uuid>",
    "status": "OK", "paypal_http_status": 201, "paypal_object_id": "1JU08902781691411",
    "amount_minor": 1500, "currency": "USD", "replayed": false } }
```
- Proposed (need service-map/contract owner approval, C10): `paypal.call_denied` (payload `tool, caller, code`), `paypal.hint_received` (payload `resource_type, resource_id`, only when webhooks enabled). Fallback: fold denials into `call_recorded` with `status=DENIED`.
- Payloads carry allowlisted fields only: no tickets, tokens, payer PII, approve-link query, `note_to_payer`.
- Consumes none.

## 10. Contract hygiene
- OpenAPI 3.1 committed under `contracts/openapi/paypal-adapter.yaml` (ADR-008); MCP tool schemas generated from the same Pydantic models; CI diff check fails on drift. Event schema under `contracts/events/`.
- Open contract items to confirm: ticket HTTP code mapping (section 7), event additions (C10), service-map tool-name update (C2).
