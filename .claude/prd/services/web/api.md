# web - BFF API consumed (through api-gateway)

Labels: V verified, VC vendor claim, I inference/unverified, P proposed (gap, not yet in service-map.md / api-gateway contract). `web` never calls mandate/checkout/resolution/shopping-agent/tracking/audit directly - every call below goes through api-gateway, which strips client identity, authenticates via cookie, and mints the internal service JWT (auth-gateway sec 2). Paths below are cited from the upstream service api.md files (mandate.md, checkout.md, resolution.md, shopping-agent.md) and from auth-gateway.md sec 2.2 route table; where api-gateway's own BFF path differs or does not exist yet, it is marked P.

## 1. Conventions for every call
- Cookie session only (no bearer tokens in the browser, REQ-WB-011). CSRF token (`X-CSRF-Token`) required on every state-changing request; sensitive flows (mandate sign, revoke, approve, offer accept) additionally require the single-use nonce from auth-gateway sec 4.
- `Idempotency-Key` (client-generated UUID) required on every mutating call (REQ-WB-051); same key + same body replays the prior response.
- All amounts in request/response bodies are integer minor units at the API layer; `web` formats to major units for display only, never sends computed money fields.
- Error body shape (uniform across upstream services): `{"error":{"code":"STABLE_CODE","message":"...","details":{}},"request_id":"..."}`. `web` maps `code` to copy-table text (spec.md sec 5/10); unmapped codes fall back to a generic "Something went wrong, nothing was charged" message (fail-closed, REQ-WB-052).
- 401 from any BFF call -> session-ended screen (spec.md sec 12). 429 -> show Retry-After-aware "slow down" message, never a silent retry storm.

## 2. Session and landing
| BFF route (gateway) | Upstream | Method | Used by screen |
|---|---|---|---|
| `/auth/demo-session` | gateway-owned | POST | Landing persona picker (buyer path) |
| `/auth/logout` | gateway-owned | POST | Any screen, logout control |
| `/auth/merchant-login` (P - not in auth-gateway route table; merchant login mechanism open per prd.md sec 8) | gateway-owned | POST | Landing persona picker (merchant path) |

Example - start buyer session:
```
POST /auth/demo-session
200 { "actor_type": "buyer", "buyer_id": "uuid", "session_epoch": 0 }
```

## 3. Mandate (buyer)
Gateway-exposed per mandate api.md sec 1: `preview`, `POST /mandates`, `GET /mandates`, `GET /mandates/{id}`, `GET /mandates/{id}/terms`, `POST .../revoke`, `GET .../verify`. `evaluate`, `summary`, reservations, grants, `/internal/*` are never exposed to `web`.

| BFF route | Upstream path | Method | Screen |
|---|---|---|---|
| `/api/mandates/preview` | `POST /mandates/preview` | POST | Mandate sign (spec.md 2.1) |
| `/api/mandates` | `POST /mandates` | POST | Mandate sign |
| `/api/mandates` | `GET /mandates` | GET | History |
| `/api/mandates/{id}` | `GET /mandates/{id}` | GET | Mandate summary |
| `/api/mandates/{id}/terms` | `GET /mandates/{id}/terms` | GET | Receipt/case screens (protection terms display) |
| `/api/mandates/{id}/revoke` | `POST /mandates/{id}/revoke` | POST | Mandate summary, Revoke |
| `/api/mandates/{id}/verify` | `GET /mandates/{id}/verify` | GET | Mandate summary (integrity check, optional display) |

Preview request/response (mandate api.md sec 4):
```json
// POST /api/mandates/preview
{
  "terms": {
    "currency": "USD",
    "max_total_minor": 6000,
    "max_qty_per_line": 2,
    "merchant_allowlist": [{"merchant_id": "shop-a", "display_name": "Shop A"}],
    "intent_text": "birthday gift for a runner",
    "expires_at": "2026-11-01T12:00:00Z",
    "protection": {"kinds_covered": ["LATE", "LOST"], "max_refund_minor": 5000, "deliver_by_days": 7},
    "revoke_effect": "FUTURE_ONLY"
  }
}
```
```json
// 200
{
  "screen_text": "DEMO MANDATE - sandbox only ...",
  "screen_text_hash": "<sha256-hex>",
  "nonce": "<base64url, shown once>",
  "nonce_expires_at": "2026-10-20T10:02:00Z",
  "policy_version": "<current>"
}
```
Client error handling: `409 NONCE_INVALID` -> silently re-call preview and re-render (user sees "terms refreshed" toast, not a hard error); `422 TERMS_OUT_OF_BOUNDS` / `UNSUPPORTED_CURRENCY` -> inline field errors from `details`; `429` -> disable Sign button with countdown.

Sign request/response (mandate api.md sec 5):
```json
// POST /api/mandates  { "Idempotency-Key": "<uuid>" }
{ "terms": { "...": "same as preview input" }, "screen_text_hash": "<echoed>", "nonce": "<from preview>" }
```
```json
// 201
{ "mandate_id": "uuid", "status": "active", "max_total_minor": 6000, "remaining_minor": 6000, "protection": {"kinds_covered": ["LATE","LOST"], "max_refund_minor": 5000, "deliver_by_days": 7}, "mandate_hash": "<sha256-hex>" }
```
Error handling: `409 IDEMPOTENCY_KEY_REUSED` with different body -> treat as a client bug, generic error; `422 SCREEN_TEXT_MISMATCH` -> force re-preview (terms changed under the buyer); `503 SIGNING_DISABLED`/`NOT_READY` -> waking-up state, retry with backoff (idempotent due to the key).

Revoke (mandate api.md sec 8):
```json
// POST /api/mandates/{id}/revoke
{ "reason_code": "BUYER_REQUEST" }
```
```json
// 200
{ "status": "revoked", "revoked_at": "2026-10-20T11:00:00Z", "released_reservations": 1, "message_code": "FUTURE_PURCHASES_STOPPED", "earned_protection_unchanged": true }
```
`message_code` maps to buyer copy (spec.md sec 2.2); `earned_protection_unchanged` drives the revoke-confirmation wording (confirmed, D1, 00-platform-prd.md).

## 4. Intent and cart (buyer) - shopping-agent + checkout
Shopping-agent's only gateway-exposed route is `POST /propose` (shopping-agent api.md sec 1). `intent-fit` is service-to-service only and never reaches `web`.

| BFF route | Upstream | Method | Screen |
|---|---|---|---|
| `/api/agent/propose` | shopping-agent `POST /propose` | POST | Intent input (spec.md 2.3) |
| `/api/carts` | checkout `POST /carts` | POST | Cart proposal / manual cart |
| `/api/carts/{id}` | checkout `GET /carts/{cart_id}` | GET | Cart screen refresh |
| `/api/carts/{id}/confirm` | checkout `POST /carts/{cart_id}/confirm` | POST | Confirm -> get `approve_url` |

Propose (shopping-agent api.md sec 4):
```json
// POST /api/agent/propose
{ "mandate_id": "uuid", "mode": "intent", "intent_text": "birthday gift for a runner under $60", "catalog_snapshot_id": "cat_v7" }
```
```json
// 200
{ "status": "OK", "source": "cached", "lines": [{"sku": "RUN-SOCKS-01", "quantity": 2, "display_title": "Running socks (2-pack)"}], "badge": "CACHED RESPONSE (recorded from live model run <date>)", "confidence": 0.82, "trace_id": "uuid" }
```
Client handling: `status != "OK"` (`NO_MATCH`/`NO_PROPOSAL`/`AI_PAUSED`) -> switch to manual catalog builder, no error UI (these are normal 200s per shopping-agent api.md sec 3). `source:"cached"` -> render `badge` verbatim. Only `{sku, qty}[]` is forwarded to `/api/carts`; `rationale`/`confidence`/`model` are display-only and never resent.

Cart create (checkout api.md sec 3):
```json
// POST /api/carts
{ "mandate_id": "uuid", "lines": [{"sku": "RUN-SOCKS-01", "qty": 2}] }
```
```json
// 201
{
  "cart_id": "uuid", "status": "BLOCKED", "currency": "USD",
  "lines": [{"sku": "RUN-SOCKS-01", "qty": 2, "unit_minor": 1500, "line_minor": 3000, "merchant_id": "shop-a"}],
  "total_minor": 3000, "remaining_cap_minor_after": 3000, "proposal_hash": "<sha256-hex>",
  "checks": [
    {"name": "MANDATE_ACTIVE", "result": "PASS", "reason_code": null, "source": "mandate"},
    {"name": "WITHIN_CAP", "result": "BLOCK", "reason_code": "OVER_CAP", "source": "mandate"}
  ],
  "intent_fit": {"verdict": "PASS", "reason_code": "OK", "advisory": true}
}
```
Client handling: `status: "BLOCKED"` -> render BLOCKED screen (spec.md 2.4), no Confirm control rendered; `status: "NEEDS_CONFIRMATION"` -> extra confirm checkbox (spec.md 2.5); 404 `MANDATE_NOT_FOUND` -> "That mandate isn't available, pick another or sign a new one."

Confirm (checkout api.md sec 4):
```json
// POST /api/carts/{id}/confirm
{ "proposal_hash": "<sha256-hex>", "confirm_intent_fit": false }
```
```json
// 201
{ "order_id": "uuid", "status": "AWAITING_APPROVAL", "approve_url": "https://www.sandbox.paypal.com/...", "total_minor": 3000, "currency": "USD" }
```
Client handling: `409 CART_CHANGED` -> re-fetch cart, show "prices or terms changed, please review again"; `409 CART_ALREADY_ORDERED` -> redirect straight to the existing order; `422 CART_BLOCKED` -> back to BLOCKED screen; `422 INTENT_FIT_CONFIRMATION_REQUIRED` -> show the confirm checkbox and resubmit; `502/503 PAYPAL_CREATE_*` -> waking/retry state, never "payment failed" (fail-closed copy). On success, navigate to the pre-redirect explainer (spec.md 2.6) before following `approve_url` through the open-redirect host allowlist check.

## 5. Return, capture, receipt (buyer) - checkout
| BFF route | Upstream | Method | Screen |
|---|---|---|---|
| `/api/orders/return` | checkout `POST /orders/return` (gateway alias of `/orders/paypal/return`) | POST | Return handler |
| `/api/orders/cancel` | checkout `POST /orders/cancel` | POST | Cancel handler |
| `/api/orders/{id}` | checkout `GET /orders/{id}` | GET | Receipt fallback polling, history |
| `/api/orders/{id}/receipt` | checkout `GET /orders/{id}/receipt` | GET | Receipt |
| `/api/orders` | checkout `GET /orders?mandate_id=&status=` | GET | History |

Return (checkout api.md sec 5):
```json
// POST /api/orders/return
{ "state": "opaque", "token": "paypal-order-id", "payer_id": "opaque" }
```
```json
// 200
{ "order_id": "uuid", "status": "CAPTURED", "receipt_url": "/orders/uuid/receipt", "message_code": "CAPTURED" }
```
Client handling per `status`/`message_code` is enumerated in spec.md sec 2.7 (NOT_APPROVED, STATE_INVALID/TOKEN_MISMATCH, SIGN_IN_REQUIRED, MANDATE_REVOKED, CAPTURE_UNKNOWN). Query string is stripped from the address bar before this call fires.

Receipt (checkout api.md sec 8):
```json
// GET /api/orders/{id}/receipt
200 {
  "order_id": "uuid", "capture_id": "...", "status": "CAPTURED", "amount_minor": 3000, "currency": "USD",
  "lines": [...], "checks": [...],
  "mandate": {"mandate_id": "uuid", "mandate_hash": "..."},
  "protection": {"window_days": 7, "protected_until_day": 7, "label": "Demo window, not PayPal's"},
  "disclosures": ["Sandbox only", "Demo protection window is illustrative", "Merchant-funded via PayPal refund"]
}
```
`404` if not yet CAPTURED -> show "Not ready yet"; `409 RECEIPT_NOT_READY` -> poll `GET /api/orders/{id}` and retry. `disclosures[]` rendered verbatim (spec.md sec 5).

## 6. Cases, offers, approvals (buyer) - resolution
Gateway additions beyond service-map.md are explicitly flagged P in resolution api.md sec 2: `/review/queue`, `/cases/{id}/review-decision`, `GET /approvals/{token}`, `/offers/{id}/decline`, `/cases/{id}/appeal`, `/controls/refunds-frozen`, `/notifications`. `web` consumes the buyer-facing subset here; merchant/reviewer subset in section 7.

| BFF route | Upstream | Method | Screen |
|---|---|---|---|
| `/api/cases/report` | resolution `POST /cases/report` | POST | Report a problem |
| `/api/cases/{id}` | resolution `GET /cases/{case_id}` | GET | Case status tracker |
| `/api/cases` | resolution `GET /cases?status=&order_id=` | GET | History |
| `/api/offers/{id}/accept` | resolution `POST /offers/{offer_id}/accept` | POST | Offer card |
| `/api/offers/{id}/decline` | resolution `POST /offers/{offer_id}/decline` | POST | Offer card |
| `/api/approvals/{token}` | resolution `GET /approvals/{token}` | GET | Out-of-terms approval preview |
| `/api/approvals/{token}/consent` | resolution `POST /approvals/{token}/consent` | POST | Out-of-terms approval confirm |
| `/api/cases/{id}/appeal` | resolution `POST /cases/{case_id}/appeal` | POST | Human-review status (add details) |
| `/api/notifications` | resolution `GET /notifications` | GET | In-app notifications badge |

Report (resolution api.md sec 3.1):
```json
// POST /api/cases/report
{ "order_id": "uuid", "text": "My package never came, it was due last week." }
```
```json
// 201
{ "case_id": "uuid", "state": "HUMAN_REVIEW", "kind": "LATE", "origin": "BUYER_REPORT",
  "reasons": [{"code": "TRIAGE_FAIL_CLOSED", "text": "A person is reviewing your case; your coverage stays active."}] }
```
Client handling: response is always 200/201 with a state, never an error for triage failure (fail-closed is a normal result); `422 TEXT_TOO_LONG` -> inline counter-based error before submit even reaches the server (client-side cap mirrors `PS_RESOLUTION_CASE_REPORT_MAX_CHARS`); `409 ORDER_NOT_CAPTURED` -> "You can report a problem once the order is complete."

Offer accept (resolution api.md sec 3.5):
```json
// POST /api/offers/{id}/accept
{ "proposal_hash": "<sha256-hex>" }
```
```json
// 200
{ "case_id": "uuid", "state": "RESOLVED_REFUNDED", "execution": "DONE", "refund": {"status": "SENT", "paypal_refund_id": "RF-123"} }
```
`409 OFFER_NOT_ACTIVE` -> re-fetch case, show current state instead of erroring (per api.md: a loser/replay gets 200 with the existing result in most cases - treat any 409 here the same way, re-GET and render); `execution: "QUEUED_FROZEN"` -> "Refunds are paused for review" (REFUNDS_FROZEN buyer-safe copy).

Approval link (resolution api.md sec 3.7):
```json
// GET /api/approvals/{token} -> 200 { "case_id": "uuid", "action": "REFUND", "amount_minor": 1000, "summary": "...", "expires_at": "...", "proposal_hash": "..." }
// POST /api/approvals/{token}/consent { "proposal_hash": "...", "csrf_nonce": "..." } -> 200 { "state": "RESOLVED_REFUNDED", "execution": "DONE" }
```
`404` -> generic "This link isn't for your session" (no existence oracle, per T10/IDOR rule); `409 APPROVAL_REPLAY` -> "Already used"; `409 APPROVAL_EXPIRED` -> "Expired, moved to review."

## 7. Merchant - orders, tracking, policy, review, audit, controls
`tracking`'s api.md has now been read (services/tracking/api.md, 2026-10-10). Routes below are re-resolved against its actual endpoints; P markers removed where tracking's contract covers the row, kept (with an explicit gap note) where it does not.

| BFF route | Upstream | Method | Screen |
|---|---|---|---|
| `/api/merchant/orders` | checkout `GET /orders?status=` (merchant min view) | GET | Orders table |
| `/api/merchant/orders/{id}` | checkout `GET /orders/{id}` (merchant min view) | GET | Order detail |
| `/api/merchant/orders/{id}/tracking` | tracking `POST /shipments` | POST | Per-row add tracking |
| `/api/merchant/orders/{id}/shipments` (new row, resolves a gap below) | tracking `GET /shipments/{order_id}` | GET | Orders table SIMULATED CARRIER status cell, order detail panel |
| `/api/demo/clock` | tracking `GET /demo/clock` (read) / `POST /demo/clock/advance` (advance) | GET / POST | Demo clock panel - current demo day display (GET) and "advance by N days" (POST) |
| `/api/demo/clock/reset` (new row, resolves a gap below) | tracking `POST /demo/clock/reset` | POST | Demo reset control (sec 3.7 spec.md), scoped to demo-flagged shipments only - distinct from the admin-token full reset at `/api/admin/demo/reset` |
| `/api/demo/carrier` | tracking `POST /demo/shipments/{id}/force` | POST | Force carrier status |
| `/api/merchant/cases/{id}` | resolution `GET /cases/{case_id}` (merchant min view) | GET | AI brief panel |
| `/api/review/queue` | resolution `GET /review/queue` | GET | Human-review queue |
| `/api/cases/{id}/review-decision` | resolution `POST /cases/{case_id}/review-decision` | POST | (reviewer action, if reviewer UI is merchant-side per prd.md sec 8) |
| `/api/cases/{id}/merchant-action` | resolution `POST /cases/{case_id}/merchant-action` | POST | Override |
| `/api/controls/refunds-frozen` | resolution `GET/PUT /controls/refunds-frozen` | GET/PUT | REFUNDS_FROZEN switch |
| `/api/audit/entries` | audit `GET /entries` | GET | Audit log grid |
| `/api/audit/verify` | audit `GET /verify` | GET | Verify-chain button |
| `/api/admin/demo/reset` | (admin-token-protected reset endpoint, sprint-plan S2-09) | POST | Demo reset control |

Add tracking (tracking api.md "POST /shipments"):
```json
// POST /api/merchant/orders/{id}/tracking
{ "order_id": "ord_1", "tracking_number": "TRK123", "carrier_name": "Demo Carrier", "outcome_profile": "ON_TIME" }
```
```json
// 201
{ "id": "shp_1", "order_id": "ord_1", "status": "LABEL_CREATED", "promised_at_sim": "...", "paypal_sync": "ADDED", "simulated": true, "carrier_label": "SIMULATED CARRIER" }
```
`outcome_profile` only accepted in PS_TRACKING_SANDBOX_MODE (always true for this demo); `paypal_sync: "FAILED"` is still a 201 (PayPal tracker failure is not a client-visible error, per tracking api.md); `409 ORDER_NOT_CAPTURED`/`DUPLICATE_TRACKING` -> inline form error; `503 DEPENDENCY_UNAVAILABLE` -> waking/retry state, nothing created.

Shipment status (tracking api.md "GET /shipments/{order_id}"):
```json
// GET /api/merchant/orders/{id}/shipments -> 200
{ "order_id": "ord_1", "sim_now": "...", "shipments": [{"id": "shp_1", "status": "IN_TRANSIT", "active": true, "promised_at_sim": "...", "anomaly": null}], "consistency": {"delivered": false, "late_detected": false, "lost_detected": false}, "simulated": true }
```
Drives the orders-table SIMULATED CARRIER status cell; `simulated: true` is always present and the badge renders it verbatim rather than inferring from field presence.

Demo clock (tracking api.md "GET /demo/clock", "POST /demo/clock/advance"):
```json
// GET /api/demo/clock -> 200 { "sim_now": "..." }
// POST /api/demo/clock { "delta_seconds": 259200, "reason": "DEMO_SKIP_TO_LATE" }  (Idempotency-Key required)
// 200 { "from_sim": "...", "to_sim": "...", "version": 7, "tick": {"applied": 3, "detected": 1} }
```
`404` if `PS_TRACKING_SANDBOX_MODE`/`PS_TRACKING_DEMO_CONTROLS_ENABLED` is off (hide the clock panel entirely rather than show a broken control); `409 CLOCK_VERSION_CONFLICT` -> re-fetch `GET /api/demo/clock` and retry; replay of the same `Idempotency-Key` returns the original body (safe to retry on timeout).

Force carrier status (tracking api.md "POST /demo/shipments/{id}/force"):
```json
// POST /api/demo/carrier { "to_status": "LOST", "reason": "DEMO_FORCE_LOST" }
// 200 { "id": "shp_1", "status": "LOST", "source": "FORCE" }
```
Explicit confirm dialog restating "this does not reflect a real carrier" (spec.md sec 3.1) before firing; `409 ILLEGAL_TRANSITION` -> "That status change isn't valid from here."

Review queue (resolution api.md sec 3.3):
```json
// GET /api/review/queue -> 200
{ "items": [{"case_id": "uuid", "kind": "OTHER", "reason_codes": ["KIND_OTHER"], "age_s": 120, "sla_state": "WITHIN", "brief": "internal text"}] }
```
Override (resolution api.md sec 3.8):
```json
// POST /api/cases/{id}/merchant-action { "type": "OVERRIDE_OFFER" }
// 200 { "case_id": "uuid", "state": "OFFERED", "offer_id": "uuid", "supersedes": "old-uuid" }
```
`409 ILLEGAL_TRANSITION` -> "This case can't be overridden right now" (state has moved; re-fetch).

REFUNDS_FROZEN (resolution api.md sec 3.11):
```json
// PUT /api/controls/refunds-frozen { "refunds_frozen": true, "reason": "manual review before demo" }
// 200 { "refunds_frozen": true, "reason": "...", "set_by": "operator", "epoch": 2 }
```
`403` -> merchant (non-operator) attempt denied, button hidden entirely for non-operator roles if the role distinction is wired; `422 REASON_REQUIRED` -> inline validation before submit.

Audit verify (service-map.md sec 2 `audit`):
```json
// GET /api/audit/verify -> 200 { "status": "OK", "head_hash": "<sha256-hex>", "epoch": 2, "entries_checked": 184 }
```
`"status": "FAILED"` -> red banner, never auto-retried silently (a judge should see this clearly if it ever happens in a scratch/demo run).

## 8. Gaps to close with the gateway owner (P items, do not invent beyond this list)
- Exact BFF path prefixes (`/api/...` here is this doc's working assumption per REQ-WB-001 "talks only to the gateway via same-origin `/api/*`") - final gateway route table may differ; this file's "BFF route" column is a proposal, not yet confirmed in service-map.md.
- **Tracking rows resolved (2026-10-10):** `services/tracking/api.md` has now been read; the add-tracking (`POST /shipments`), shipment-status (`GET /shipments/{order_id}`), demo-clock read/advance (`GET /demo/clock`, `POST /demo/clock/advance`), and force-carrier (`POST /demo/shipments/{id}/force`) rows in section 7 are no longer P - their upstream shapes are confirmed and reproduced above. Remaining tracking-side gaps, not invented here:
  - `POST /demo/clock/reset` is tracking's own endpoint (resets demo-flagged shipments' scripts/detections only); it is distinct from `/api/admin/demo/reset` (the full chain-epoch reset, sprint-plan S2-09) - whether the merchant-facing demo clock panel exposes a separate "reset clock only" control, or only the full reset exists in the UI, is a UI-design decision, not a contract gap, and is left to implementation (spec.md sec 3.7/8 does not currently distinguish the two).
  - `GET /shipments/{order_id}/verify?claim=` (consistency check against a buyer claim) is `internal (resolution), merchant`-scoped per tracking api.md but has no BFF row here because no web screen currently surfaces it directly (resolution consumes it server-side); flagged here only so a future screen doesn't assume it's missing by design versus simply unused by `web` today.
  - Tracking's `shipment.late_detected`/`shipment.lost_detected` events are consumed by `resolution`/`audit`, never by `web` directly (web has no event/webhook consumption model) - no BFF row needed.
- Merchant login mechanism (one-click vs password) affects `/auth/merchant-login` only; no other row changes either way.
- Reviewer-decision route (`/api/cases/{id}/review-decision`) is included because resolution api.md defines it, but prd.md sec 8 leaves open whether reviewer is a separate login or a merchant-side screen; this file assumes merchant-side per the PRD's stated default.
