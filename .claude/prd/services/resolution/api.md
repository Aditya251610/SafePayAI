# resolution: API

Labels V/VC/I. Machine-readable truth: FastAPI-generated OpenAPI 3.1 committed at `contracts/openapi/resolution.json`; events at `contracts/events/*.v1.json`; CI fails on drift (ADR-008). This file is the human summary. Behavior rules live in spec.md (section numbers cited as spec s#). Service-map and adr.md win on conflicts (spec s15).

## 1. Conventions
- Callers: api-gateway (user-originated; internal JWT `aud=resolution`, `act.role` buyer|merchant|reviewer|operator) and services (`svc:*`). The browser never calls resolution directly. Gateway edge routes map to the upstream paths below (spec C1).
- Headers: `Authorization: Bearer <internal JWT>`, `X-Request-Id`, `traceparent`, `Idempotency-Key` (required on every mutating public POST/PUT), `Content-Type: application/json`.
- Bodies use `extra=forbid`. Client-sent `amount`, `amount_minor`, `currency`, `merchant`, `capture_id`, `buyer_id`, `state` are rejected with 422 `FIELD_NOT_ALLOWED` (REQ-RS-021; test T22). Money is integer minor units; currency comes from the capture.
- Error body: `{"error": {"code": "STABLE_CODE", "message": "human text", "details": {}}, "request_id": "..."}`. Messages shown to a buyer pass the banned-word gate (spec s11).
- Ownership: buyer_id from the token only; wrong owner returns 404 (not 403) to avoid enumeration (T10).
- Roles: B buyer (owner), M merchant (shared demo login, disclosed), R reviewer (self-asserted name, disclosed), O operator (never a merchant login), S service `svc:*`, SYS scheduled job (`TICK` secret or `svc:poller`).
- Idempotency: see section 4. Safety never depends only on the header; state CAS, row locks and unique constraints are the backstop (spec s13).

## 2. Endpoints
| Method, path | Roles | Purpose |
|---|---|---|
| POST `/cases/report` | B | Buyer problem text (untrusted) -> case + triage |
| GET `/cases/{case_id}` | B(own), M(min fields), R, O, S | Case, timeline, current offer, reasons |
| GET `/cases?status=&order_id=` | M, R, O, S, B(own) | List |
| GET `/review/queue` | R, O | HUMAN_REVIEW items oldest first, age, SLA timer |
| POST `/cases/{case_id}/review-decision` | R | PROPOSE_REFUND / PROPOSE_RESHIP / DECLINE / CLOSE |
| POST `/offers/{offer_id}/accept` | B | Tier 1 accept (T9) |
| POST `/offers/{offer_id}/decline` | B | Buyer declines (T11); reason enum |
| GET `/approvals/{token}` | B | Preview exactly what the link approves (no state change) |
| POST `/approvals/{token}/consent` | B | Tier 2 single-use consent bound to `proposal_hash` |
| POST `/cases/{case_id}/merchant-action` | M | `OVERRIDE_OFFER` or `CONFIRM_RESHIP` |
| POST `/cases/{case_id}/appeal` | B | DECLINED -> HUMAN_REVIEW (T24) |
| POST `/refunds/reconcile` | SYS, O | Resolve SENT/UNKNOWN attempts |
| GET `/controls/refunds-frozen` | O, R, S | Read kill-switch state (never cached beyond TTL) |
| PUT `/controls/refunds-frozen` | O | Freeze/unfreeze with reason |
| GET `/notifications` | B(own), M | In-app notifications |
| POST `/internal/events` | S | Event inbox (HMAC/internal token) |
| GET `/internal/outbox?after=seq` | S | Pull catch-up (ADR-003) |
| POST `/internal/outbox/flush` | SYS | Relay now (cron safe) |
| POST `/internal/tick` | SYS | Reconcile + outbox flush + window checks |
| GET `/healthz`, `/readyz`, `/health`, `/health/deep` | none/SYS | Liveness; DB + flag readable; aliases (spec C8) |

Additions beyond service-map (flagged, spec C1): `/review/queue`, `/cases/{id}/review-decision`, `GET /approvals/{token}`, `/offers/{id}/decline`, `/cases/{id}/appeal`, `/controls/refunds-frozen`, `/notifications`. `/internal/*` is never routed by the gateway (404 externally).

## 3. Endpoint detail

### 3.1 POST /cases/report (B)
Request
```json
{"order_id": "uuid", "text": "My package never came, it was due last week."}
```
- `text` length-capped by `PS_RESOLUTION_CASE_REPORT_MAX_CHARS`; stored as `untrusted_text`, HTML escaped on render, never executed or put in a prompt as instructions.
- `kind` is NOT accepted from the client; it comes only from `triage-ai` (enum) or the detector.

Response 201 (new case) or 200 (existing case for `(order_id, kind)`; no duplicate)
```json
{
  "case_id": "uuid",
  "state": "TRIAGED | HUMAN_REVIEW | OFFERED",
  "kind": "LATE | LOST | DAMAGED | WRONG_ITEM | NOT_AS_DESCRIBED | OTHER",
  "origin": "BUYER_REPORT",
  "reasons": [{"code": "TRIAGE_FAIL_CLOSED", "text": "A person is reviewing your case; your coverage stays active."}],
  "offer": null,
  "protection": {"window_hold": true}
}
```
- Injection or triage failure yields `HUMAN_REVIEW`, never a denial (REQ-RS-004, T7/T8).
Codes: 201, 200, 400 `VALIDATION_ERROR`, 401, 403 `ROLE_NOT_ALLOWED`, 404 `ORDER_NOT_FOUND` (also wrong owner), 409 `ORDER_NOT_CAPTURED`, 422 `FIELD_NOT_ALLOWED`, 422 `TEXT_TOO_LONG`, 422 `IDEMPOTENCY_KEY_REUSED`, 429, 503 `DEPENDENCY_UNAVAILABLE` (only if resolution cannot write its own DB; downstream failures route the case to HUMAN_REVIEW with 201).

### 3.2 GET /cases/{case_id}
Response 200
```json
{
  "case_id": "uuid", "order_id": "uuid", "state": "OFFERED", "version": 3,
  "kind": "LATE", "origin": "DETECTOR",
  "opened_at": "iso8601", "window_hold": true,
  "timeline": [{"from": "MONITORING", "to": "PROBLEM_DETECTED", "actor": "system", "reason": "materialized", "at": "iso8601"}],
  "decision": {"class": "INSIDE_TERMS", "policy_version": "pinned", "reasons": [{"code": "IN_TERMS"}], "illustrative": true},
  "offer": {"offer_id": "uuid", "action": "REFUND", "amount_minor": 0, "currency": "USD", "tier": "CONFIRM", "status": "ACTIVE", "proposal_hash": "sha256-hex", "expires_at": "iso8601"},
  "refund": {"status": "NONE | REQUESTED | SENT | COMPLETED | FAILED | UNKNOWN | NOT_SENT", "paypal_refund_id": null},
  "queued_reason": null
}
```
- Numbers are placeholders. Merchant view omits `untrusted_text`, reviewer brief and buyer identifiers (minimum fields). `queued_reason` is `REFUNDS_FROZEN` when an APPROVED case waits on the kill switch.
Codes: 200, 401, 403, 404.

### 3.3 GET /review/queue (R, O)
Response 200
```json
{"items": [{"case_id": "uuid", "kind": "OTHER", "reason_codes": ["KIND_OTHER"], "entered_at": "iso8601", "age_s": 0, "sla_target_s": null, "sla_state": "NO_TARGET | WITHIN | OVER", "brief": "internal text or static fallback"}]}
```
- `sla_target_s` is a demo target (I), null when `PS_RESOLUTION_HUMAN_REVIEW_SLA_TARGET_S` is unset. Brief is internal only, never shown to buyers.

### 3.4 POST /cases/{case_id}/review-decision (R)
Request
```json
{"decision": "PROPOSE_REFUND", "reviewer_name": "self-asserted text", "reason": "required for DECLINE and CLOSE"}
```
- `decision` in `PROPOSE_REFUND | PROPOSE_RESHIP | DECLINE | CLOSE`. No amount field: amount is derived (full-order rule, spec s4).
Response 200: `{"case_id": "...", "state": "OFFERED | DECLINED | CLOSED", "offer_id": "uuid-or-null"}`
- `PROPOSE_*` creates an offer/proposal (tier 1 or 2); the reviewer cannot execute a refund (T13, T14, T15).
Codes: 200, 403 `ROLE_NOT_ALLOWED`, 404, 409 `ILLEGAL_TRANSITION`, 409 `CONCURRENT_MODIFICATION`, 422 `REASON_REQUIRED`, 422 `FIELD_NOT_ALLOWED`.

### 3.5 POST /offers/{offer_id}/accept (B)
Request: `{"proposal_hash": "sha256-hex"}`
Response 200
```json
{"case_id": "uuid", "state": "APPROVED | REFUNDING | RESOLVED_REFUNDED | RESOLVED_RESHIP", "execution": "DONE | IN_PROGRESS | QUEUED_FROZEN | NOT_STARTED", "refund": {"status": "SENT", "paypal_refund_id": null}}
```
- Exactly one accept wins (conditional UPDATE). A loser, a second tab or a replay gets 200 with the existing result, not an error (spec s13, C19).
- Execution runs inline after approval; if frozen the case stays `APPROVED`, `execution=QUEUED_FROZEN` (E9). If `core` times out mid-saga the persisted state is resumed by reconcile.
Codes: 200, 404, 409 `OFFER_NOT_ACTIVE` (superseded/expired), 409 `PROPOSAL_HASH_MISMATCH`, 409 `ILLEGAL_TRANSITION`, 422, 423 not used (freeze is not an error).

### 3.6 POST /offers/{offer_id}/decline (B)
Request: `{"reason_code": "NOT_WANTED | WANT_HUMAN | OTHER"}` -> 200 `{"state": "DECLINED"}`. Buyer-initiated only. Codes: 200, 404, 409, 422.

### 3.7 GET /approvals/{token} and POST /approvals/{token}/consent (B)
GET returns exactly what the link approves; no state change.
```json
{"case_id": "uuid", "action": "REFUND", "amount_minor": 0, "currency": "USD", "summary": "server template text", "expires_at": "iso8601", "proposal_hash": "sha256-hex"}
```
POST request (CSRF nonce per auth-gateway 4.2): `{"proposal_hash": "sha256-hex", "csrf_nonce": "string"}`
Response 200: `{"case_id": "uuid", "state": "APPROVED | REFUNDING | RESOLVED_REFUNDED", "execution": "DONE | IN_PROGRESS | QUEUED_FROZEN"}`
- Redeem is a conditional single-row UPDATE; replay returns 409 `APPROVAL_REPLAY` plus an audit event (T2). Session buyer must equal `cases.buyer_id` (IDOR returns 404). Tampered or stale hash returns 409 `PROPOSAL_HASH_MISMATCH` (T3). Expired link moves the case to HUMAN_REVIEW (T12), never deny.
Codes: 200, 401, 404, 409 `APPROVAL_REPLAY` | `PROPOSAL_HASH_MISMATCH` | `APPROVAL_EXPIRED` | `APPROVAL_REVOKED`, 422.

### 3.8 POST /cases/{case_id}/merchant-action (M)
Request: `{"type": "OVERRIDE_OFFER"}` or `{"type": "CONFIRM_RESHIP"}`. No amount accepted.
Response 200: `{"case_id": "uuid", "state": "OFFERED | RESOLVED_RESHIP", "offer_id": "uuid", "supersedes": "uuid-or-null"}`
- Override builds a NEW offer with a NEW `proposal_hash`, marks the old one SUPERSEDED, revokes old tokens, always tier 2; merchant cannot approve it (T18, T26). Stamps `merchant_shared`.
Codes: 200, 403, 404, 409 `ILLEGAL_TRANSITION`, 422.

### 3.9 POST /cases/{case_id}/appeal (B)
Request: `{"note": "optional untrusted text"}` -> 200 `{"state": "HUMAN_REVIEW"}` (T24). Codes: 200, 404, 409.

### 3.10 POST /refunds/reconcile (SYS, O)
Request: `{"limit": 25}` optional.
Response 200: `{"examined": 0, "finalized_completed": 0, "finalized_failed": 0, "still_unknown": 0, "needs_review": 0, "frozen_skipped_replays": 0}`
- Idempotent and safe to call repeatedly or concurrently (`FOR UPDATE SKIP LOCKED`). While frozen it still reads (GET refund) but never replays (spec s8).

### 3.11 GET/PUT /controls/refunds-frozen
GET 200: `{"refunds_frozen": true, "reason": "text", "set_by": "operator", "set_at": "iso8601", "epoch": 0, "adapter_mirror": "ACKED | PENDING", "readable": true}`
PUT request: `{"refunds_frozen": false, "reason": "required, free text, audited"}`
- Only role operator; merchant gets 403 (T18). Unfreeze requires a non-empty reason. Response is the new GET body. Each toggle emits `refund.freeze_changed` and pushes the mirror to the adapter until ACKED (spec s9, C3).
- If the flag row is absent or unreadable the service reports `refunds_frozen=true, readable=false` and all gates stay closed.
Codes: 200, 403, 422 `REASON_REQUIRED`.

### 3.12 Health
- `/healthz` liveness, no DB. `/readyz` checks DB and that the flag is readable (flag unreadable = not ready for money, still 200 with `money_enabled=false` so the app stays up); `/health` alias of healthz; `/health/deep` alias of readyz plus dependency flags (touches DB; ping only in review windows, see deployment.md).

## 4. Idempotency
- Header `Idempotency-Key` required on all mutating public calls; table `idempotency_keys` unique on `(key, route, principal)`. Same key + same body returns the stored response (HTTP status and body identical); same key + different body returns 422 `IDEMPOTENCY_KEY_REUSED`; missing key returns 400 `IDEMPOTENCY_KEY_REQUIRED` (exempt: `/internal/*`, reconcile, which are naturally idempotent).
- Domain idempotency (independent of the header): unique `(order_id, kind)` for cases; one refund per case; offer accept and approval redeem are conditional UPDATEs; `inbox_dedupe.event_id` unique; PayPal `request_id` persisted before the call (V PayPal behavior: replay returns the original refund, 409 on concurrent identical).

## 5. Error code catalogue
`VALIDATION_ERROR`, `FIELD_NOT_ALLOWED`, `IDEMPOTENCY_KEY_REQUIRED`, `IDEMPOTENCY_KEY_REUSED`, `ROLE_NOT_ALLOWED`, `ORDER_NOT_FOUND`, `ORDER_NOT_CAPTURED`, `TEXT_TOO_LONG`, `ILLEGAL_TRANSITION` (409), `CONCURRENT_MODIFICATION` (409), `OFFER_NOT_ACTIVE`, `PROPOSAL_HASH_MISMATCH`, `APPROVAL_REPLAY`, `APPROVAL_EXPIRED`, `APPROVAL_REVOKED`, `REASON_REQUIRED`, `DEPENDENCY_UNAVAILABLE`. No stack traces or internal paths in any body (T21).

## 6. Outbox events (envelope per overview s7: `event_id, type, version, occurred_at, producer, aggregate_id, trace_id, payload`)
Delivery: Postgres transactional outbox written in the same transaction as the state change, HTTP push, pull catch-up (ADR-003); at-least-once, consumers dedupe by `event_id`. Payloads carry ids, state, reason codes, minor-unit amounts; no free text, tokens, secrets or PII beyond ids.

| Event (producer resolution) | Emitted when | Payload keys (summary) | Consumers |
|---|---|---|---|
| `case.opened` | case materialized (lazy, spec s3) | case_id, order_id, kind, origin | audit |
| `case.triaged` | T5/T6 | case_id, kind, confidence, injection_suspected, outcome | audit |
| `case.state_changed` | every transition (additive, spec C5) | case_id, from, to, actor, reason_code, version | audit |
| `case.resolved` | T18, T10 | case_id, path, resolved_at | audit |
| `offer.created` | T7, T13, T25, T26 | offer_id, action, amount_minor, currency, tier, proposal_hash | audit |
| `approval.granted` | T9 | case_id, offer_id, basis, proposal_hash | audit |
| `refund.requested` | check 9 commit | case_id, attempt_id, request_id, invoice_id, amount_minor | audit |
| `refund.completed` | T18 | case_id, attempt_id, paypal_refund_id | audit |
| `refund.failed` | T19 | case_id, attempt_id, reason_code | audit |
| `refund.unknown` | UNKNOWN / reconcile mismatch | case_id, attempt_id, reconcile_count | audit |
| `refund.freeze_changed` | each toggle (additive, spec C5) | refunds_frozen, epoch, set_by_role, reason_code | audit |

Consumed (inbox, deduped by `event_id`; handler is a no-op if the case exists):
| Event | Producer | Handling |
|---|---|---|
| `shipment.late_detected` | tracking | open case kind LATE (idempotent on `(order_id, kind)`), run triage-optional path, decide |
| `shipment.lost_detected` | tracking | open case kind LOST; if a LATE case is open, escalate (P2, T27) |
| `mandate.revoked` | mandate | blocks pre-authorization for cases not yet opened; opened cases keep their terms snapshot (spec C6 — confirmed, D1, 00-platform-prd.md: revoke = future spend only, earned protection stands) |

Resolution calls these downward only and is never called synchronously by tracking/mandate/checkout (events instead).

## 7. Downstream calls (for contract tests; not public)
`triage-ai` (`/classify`, `/draft`, `/brief`), `mandate` (`GET /mandates/{id}/terms`, status), `checkout` (`GET /orders/{id}`), `tracking` (`GET /shipments/{order_id}`), `paypal-adapter` (`refund_capture`, `get_refund`, `get_capture`, `reconcile_refund` pending adapter owner, spec C4, and `PUT /v1/controls/refunds-frozen` mirror). Any failure, timeout or schema error returns FAIL for that fact, which becomes HUMAN_REVIEW or a blocked check.
