# Service map (FINAL: 10 backend/edge services + 1 web app = 11 slugs)

Labels: V verified, VC vendor claim, I inference/assumption. Slugs match `service-list.txt`.

## 1. Summary table

| slug | role (one line) | PayPal creds | LLM | money path |
|---|---|---|---|---|
| api-gateway | Single entry: auth, sessions, internal-token minting, routing, rate limit, BFF aggregation | no | no | yes (gate) |
| mandate | Mandate lifecycle + deterministic cart evaluation | no | no | yes |
| catalog | Seeded items, merchants, authoritative prices | no | no | yes (prices) |
| shopping-agent | Intent -> structured cart proposal; advisory intent-fit | no | YES | no (advisory only) |
| checkout | Cart check orchestration, order + capture orchestration, receipt | no | no | yes |
| paypal-adapter | REST wrapper + our own MCP server; ONLY holder of PayPal creds | YES | no | yes |
| tracking | Simulated carrier, demo clock, late/lost detector | no | no | no (emits signals) |
| resolution | Case state machine, policy engine, offers, approvals, refund orchestration | no | no | yes |
| triage-ai | Classify text, draft messages, reviewer brief | no | YES | no |
| audit | Append-only hash chain + verify | no | no | integrity (not on money path) |
| web | Buyer + merchant UI (one Next.js app, two route groups) | no | no | no |

Merges (why): demo-control/clock folded into `tracking` (it owns time); notifications folded into `resolution` (in-app only, no email service; email is out of scope, I); merchant UI and buyer UI are one `web` deployable (two route groups, one build, one cold start); order + checkout merged (one aggregate lifecycle, avoids a distributed transaction between cart and order). Splits (why): `paypal-adapter` separate = credential blast-radius boundary + MCP surface; `triage-ai` separate from `shopping-agent` = different prompts, different trust data, different fail-closed behavior, and neither can reach the other's tools; `audit` separate = DB role is INSERT/SELECT only and no one else may write chain rows; `mandate` separate from `checkout` = mandate is the hero artifact with its own invariants and the thing judges inspect.

## 2. Per service

### api-gateway
- Role: verify the user session (see ADR-006), mint a short-lived internal JWT (aud per service, claims: sub, role buyer|merchant, mandate_id optional, jti), route `/api/<svc>/*`, rate limit, CORS, request-id, BFF endpoints that fan out for UI screens (read-only aggregation).
- Owns: `gateway` schema: users (2-3 seeded demo accounts), sessions, signing keys metadata. No business data.
- Sync exposes: public REST for web; `/.well-known/jwks.json`.
- Sync consumes: every service (proxy/BFF).
- Events: none emitted; none consumed.
- Criticality: money path (everything passes through; failure = demo down). Keep it tiny and stateless apart from sessions.
- NOT its job: business rules, mandate checks, price math, calling PayPal or LLM, writing audit.

### mandate
- Role: create/sign (HMAC, demo-grade), store, revoke, expire mandates; expose deterministic `evaluate(cart)` returning hard-block reasons.
- Owns: `mandate` schema: mandates (immutable terms + hash + hmac), revocations, nonces, protection_terms, outbox.
- Sync exposes: `POST /mandates`, `GET /mandates/{id}`, `POST /mandates/{id}/revoke`, `POST /mandates/{id}/evaluate` (input: server-priced cart; output: allow/block + reasons[]), `GET /mandates/{id}/terms`.
- Sync consumes: none (pure; receives prices in the request so it has no catalog dependency).
- Events emitted: `mandate.signed`, `mandate.revoked`, `mandate.expired`.
- Consumes: none.
- Money path: yes (it is the authority on what may be spent/refunded).
- NOT its job: pricing, recommending items, LLM judgement, refund execution, deciding refund policy.

### catalog
- Role: ~12 seeded items, 3 virtual merchants -> one sandbox merchant; authoritative prices in integer minor units.
- Owns: `catalog` schema: merchants, items, categories, merchant_settlement_map. Read-only at runtime (seeded by migration).
- Sync exposes: `GET /items`, `GET /items/{id}`, `POST /prices/resolve` (sku+qty list -> priced lines).
- Consumes: none. Events: none (static data; version field only).
- Money path: yes (price truth). Item descriptions are untrusted text when fed to an LLM.
- NOT its job: ranking, cart logic, inventory, merchant onboarding.

### shopping-agent
- Role: turn buyer intent into `{sku, qty}[]` JSON (schema-validated), plus advisory intent-fit (PASS | NEEDS_BUYER_CONFIRMATION | REJECT_WITH_REASON) that can only tighten.
- Owns: `agent` schema: proposal_log (prompt hash, model id, output, validation result, latency). No money data.
- Sync exposes: `POST /propose` (intent, mandate summary, catalog snapshot id -> cart proposal), `POST /intent-fit`.
- Consumes: catalog (read items), mandate (read-only summary) via gateway token; LLM provider.
- Events: emits `cart.proposed` (for audit). Consumes none.
- LLM: yes. No PayPal creds, no write tool to any money service; output is data, never executed directly.
- Money path: no (advisory); its failure degrades to manual cart / NEEDS_BUYER_CONFIRMATION.
- NOT its job: prices, hard checks, creating orders, any refund decision.

### checkout
- Role: single owner of cart -> check -> order -> capture. Re-prices via catalog, runs mandate evaluate, calls shopping-agent intent-fit only after hard checks pass, creates PayPal order via adapter, handles return/capture, stores receipt + protection window.
- Owns: `checkout` schema: carts, cart_checks, orders, captures (capture_id, custom_id=mandate_id, invoice_id), receipts, idempotency_keys, outbox.
- Sync exposes: `POST /carts` (propose+check), `POST /carts/{id}/confirm`, `POST /orders/{id}/capture`, `GET /orders/{id}`, `GET /orders?mandate_id=`.
- Sync consumes: catalog, mandate, shopping-agent (advisory), paypal-adapter.
- Events emitted: `cart.checked`, `order.created`, `order.captured`, `order.capture_failed`. Consumes: `mandate.revoked` (blocks un-captured carts).
- Money path: yes. Server derives merchant/amount/currency/capture_id; client-supplied values ignored.
- NOT its job: refunds, carrier status, holding PayPal secrets, LLM calls.

### paypal-adapter
- Role: thin typed wrapper over verified REST calls (OAuth token cache, create order, get order, capture, add tracking, refund, get refund, get capture) AND our own MCP server exposing the same minimal tools. Persists every outbound call (request_id, hash of body, status, response id) in an idempotency ledger.
- Owns: `paypal` schema: token cache (memory preferred; no secret in DB), call_ledger, refund_ledger. Credentials only in this service's platform env.
- Sync exposes: internal REST `/v1/orders`, `/v1/orders/{id}/capture`, `/v1/orders/{id}/track`, `/v1/captures/{id}/refund`, `/v1/refunds/{id}`; MCP at `/mcp` (tools: create_order, get_order, capture_order, add_tracking, refund_capture, get_refund). MCP is reachable only with an internal token whose caller is allowlisted per tool (checkout: orders/capture only; tracking: add_tracking/get_tracking (least privilege — corrected 2026-10-10 per paypal-adapter spec.md C5, this doc previously said checkout); resolution: refund_capture/get_refund; nobody else; LLM services: none).
- Consumes: PayPal sandbox REST (V behaviors in brief section 3).
- Events: emits `paypal.call_recorded` (for audit). Consumes none.
- Defense in depth: requires caller-supplied `request_id`, rejects missing; per-call refund ceiling from config; treats 409 as in-progress and returns UNKNOWN (never retries blind).
- Money path: yes (it IS the money hands). NOT its job: deciding anything, mandate/policy logic, LLM calls, any PayPal feature in the gated list (Fastlane, Vault v3, etc.).

### tracking
- Role: SIMULATED carrier state machine per shipment, demo clock (offset controllable), detector/poller that emits late/lost signals, merchant "add tracking" entry, demo-control endpoints (advance clock, force late/lost).
- Owns: `tracking` schema: shipments, shipment_events, demo_clock, detector_runs, outbox.
- Sync exposes: `POST /shipments` (merchant adds tracking; also calls adapter `add_tracking` as a "tracking added" signal), `GET /shipments/{order_id}`, `POST /demo/clock/advance`, `POST /demo/shipments/{id}/force`, `POST /detector/run` (idempotent; also called by a free external cron or by the scheduled loop).
- Sync consumes: paypal-adapter (add_tracking), checkout (read order/promise date).
- Events emitted: `shipment.created`, `shipment.status_changed`, `shipment.late_detected`, `shipment.lost_detected`. Consumes: `order.captured`.
- Money path: no (signals only; wrong signal cannot move money by itself; resolution re-verifies).
- NOT its job: refund decisions, claiming real carrier data (always labelled SIMULATED CARRIER), PayPal tracker status (PayPal cannot represent late/lost, V).

### resolution
- Role: case state machine (PROTECTED..CLOSED), deterministic merchant policy (3 hardcoded rules), offers, approval links (single-use, bound by proposal_hash), 9 ordered pre-refund checks, refund saga, human-review queue, in-app notifications.
- Owns: `resolution` schema: cases, case_transitions, offers, approvals, policy_decisions, refund_attempts (persisted request_id BEFORE call), notifications, outbox.
- Sync exposes: `POST /cases/report` (buyer free text, untrusted), `GET /cases/{id}`, `GET /cases?status=`, `POST /offers/{id}/accept`, `POST /approvals/{token}/consent`, `POST /cases/{id}/merchant-action` (override creates NEW offer needing buyer approval), `POST /refunds/reconcile`.
- Sync consumes: triage-ai (classify, fail closed), mandate (terms, status), checkout (order/capture facts), tracking (shipment facts), paypal-adapter (refund, get_refund).
- Events emitted: `case.opened`, `case.triaged`, `offer.created`, `approval.granted`, `refund.requested`, `refund.completed`, `refund.failed`, `refund.unknown`, `case.resolved`. Consumes: `shipment.late_detected`, `shipment.lost_detected`, `mandate.revoked`.
- Money path: yes (the decision point). AI output is only an input field (category, confidence); amounts come from policy + mandate terms + capture.
- NOT its job: LLM calls (it calls triage-ai), PayPal credentials, carrier simulation, price truth.

### triage-ai
- Role: classify free text into the enum + confidence; draft buyer/merchant messages (output gated: no URLs/amounts); reviewer brief (read-only summary).
- Owns: `triage` schema: triage_log (input hash, model id, output, validation result). 
- Sync exposes: `POST /classify`, `POST /draft`, `POST /brief`.
- Consumes: LLM provider only. Receives data in the request body (no outbound service calls, so no ambient read access to other services).
- Events: emits `triage.completed` (for audit). Consumes none.
- LLM: yes. No PayPal creds, no money API. Any schema failure, timeout, or low confidence returns `OTHER/HUMAN_REVIEW` (fail closed).
- Money path: no.
- NOT its job: amounts, approving, sending anything, calling other services.

### audit
- Role: append-only hash-chained log of mandate, cart, order, refund (and AI proposals) events; verify-chain endpoint.
- Owns: `audit` schema: entries (seq, prev_hash, hash, event_id, type, payload JSON, ts). Triggers block UPDATE/DELETE; the service's DB role is INSERT/SELECT only (V as a design; to be verified on chosen host).
- Sync exposes: `POST /append` (internal, idempotent on event_id), `GET /entries`, `GET /verify`.
- Consumes: all domain events (HTTP push; it is a subscriber with a pull-backfill).
- Events: none emitted.
- Money path: no (observer). Not fail-closed: if audit is down, events queue in producers' outboxes; however resolution refuses to START a refund if its own `refund.requested` event cannot be durably written to its outbox (outbox is local, so this is normally always possible).
- NOT its job: business decisions, mutation of any record, claiming "tamper-proof" (it is tamper-evident for demo; DB owner can still rewrite).

### web
- Role: buyer screens (sign mandate, intent, cart + reasons, checkout, receipt, report problem, approve offer) and merchant screens (add tracking, case queue, review brief, override); SIMULATED CARRIER and sandbox banners; demo-control panel (clock).
- Owns: nothing (no DB). Talks only to api-gateway.
- Money path: no. NOT its job: any authorization logic, price calc, secrets.

## 3. Dependency graph (sync calls; arrow = "calls")

```
web -> api-gateway -> {mandate, catalog, shopping-agent, checkout, tracking, resolution, audit(read)}
shopping-agent -> catalog, mandate(read), LLM
checkout -> catalog, mandate, shopping-agent(advisory), paypal-adapter
tracking -> paypal-adapter, checkout(read)
resolution -> triage-ai, mandate, checkout(read), tracking(read), paypal-adapter
triage-ai -> LLM
paypal-adapter -> PayPal sandbox
all services --(outbox events HTTP push)--> audit ; tracking->resolution ; checkout->tracking ; mandate->{checkout,resolution}
```
- No cycles in sync calls (rule: sync call direction is downward only; upward communication is by event).
- Max sync depth on any request: 3 (gateway -> resolution -> adapter).
- Credential boundary: only paypal-adapter. LLM boundary: only shopping-agent and triage-ai.

## 4. Event ownership matrix

| event | producer | consumers |
|---|---|---|
| mandate.signed / revoked / expired | mandate | audit, checkout (revoked), resolution (revoked) |
| cart.proposed | shopping-agent | audit |
| cart.checked | checkout | audit |
| order.created / captured / capture_failed | checkout | audit, tracking (captured) |
| shipment.created / status_changed | tracking | audit |
| shipment.late_detected / lost_detected | tracking | resolution, audit |
| case.* / offer.created / approval.granted | resolution | audit |
| refund.requested / completed / failed / unknown | resolution | audit |
| triage.completed | triage-ai | audit |
| paypal.call_recorded | paypal-adapter | audit |
