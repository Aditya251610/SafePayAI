# Architecture overview: SafePayAI (microservices, zero-cost, Python/FastAPI)

Labels: V verified, VC vendor claim, I inference/unverified. Free-tier limits below are all I (not re-verified today); an infra agent must re-check before committing.

## 1. System context
- Actors: buyer, merchant (single shared sandbox merchant login, not per-merchant accountability), PayPal sandbox (REST), one LLM provider, demo operator.
- External: PayPal sandbox REST (only via `paypal-adapter`); LLM API (only `shopping-agent`, `triage-ai`); hosting + Postgres free tiers.
- Everything user-facing goes through `api-gateway`. Services never trust network position; they trust only a signed internal token.

## 2. Principles
- P1 AI never decides money; AI services have no PayPal creds and no route to money APIs.
- P2 Server derives merchant, amount, currency, capture_id. Clients/models only name SKUs, quantities, and intent.
- P3 Fail closed: unknown or error -> block or HUMAN_REVIEW, never allow.
- P4 One owner per datum; other services read via API or event copies, never by SQL.
- P5 Sync calls go downward only (no cycles); upward by event.
- P6 Simplest consistency that is safe: local transaction + outbox, idempotent consumers, one saga (refund).
- P7 Code boundaries are independent of deployment boundaries (Profile A vs B).
- P8 Honest labelling: SIMULATED CARRIER, sandbox, seeded catalog, "merchant-funded via PayPal refund".

## 3. Bounded contexts
| context | service(s) | core language |
|---|---|---|
| Identity and access | api-gateway | session, role, internal token |
| Authorization of spend (the Mandate) | mandate | mandate, terms, evaluation |
| Offer and pricing | catalog | item, merchant, price |
| Proposal | shopping-agent | intent, proposal, intent-fit |
| Purchase | checkout, paypal-adapter | cart, order, capture, receipt |
| Fulfilment signal | tracking | shipment, carrier event, clock |
| Resolution (SafePayAI loop) | resolution, triage-ai | case, offer, approval, refund |
| Integrity | audit | entry, chain |
Context map: paypal-adapter is an anti-corruption layer over PayPal (its models never leak: others see our own order/refund DTOs). Others are customer/supplier with explicit OpenAPI contracts. Rich domain modeling applies to mandate and resolution only; the rest are thin CRUD/transaction scripts (no DDD ceremony there).

## 4. Key request flows
Notation: GW = api-gateway. Every call GW -> svc carries the internal token.

### F1 Sign mandate
1. web -> GW `POST /mandates` (merchants, max_total, intent, expiry, protection terms).
2. GW -> mandate: validates terms, assigns nonce + policy_version, canonical-JSON hash, HMAC, stores, writes outbox `mandate.signed` in the same transaction.
3. Outbox relay pushes `mandate.signed` -> audit.
4. Failure: mandate down -> 503, nothing created. Idempotency-Key on POST prevents double mandates.

### F2 Agent proposes cart + checks
1. web -> GW -> shopping-agent `/propose` (intent + mandate summary). Agent reads catalog, calls LLM, validates output against JSON schema (SKU in catalog, qty int). Invalid -> one retry -> else "no proposal" (manual cart).
2. web -> GW -> checkout `POST /carts` with only `{sku, qty}[]` + mandate_id.
3. checkout re-prices via catalog `/prices/resolve` (agent-stated price ignored; if the proposal carried a price that differs, record hard-block `PRICE_MISMATCH`).
4. checkout -> mandate `/evaluate`: deterministic hard checks (revoked/expired, merchant allowlist, cap incl. fees, unknown SKU, qty cap, currency).
5. If no hard block: checkout -> shopping-agent `/intent-fit` (advisory). Result may only tighten: PASS / NEEDS_BUYER_CONFIRMATION / REJECT_WITH_REASON. Timeout/error -> NEEDS_BUYER_CONFIRMATION.
6. checkout stores cart + check reasons, emits `cart.checked`, returns reasons to UI.
- Fail closed: mandate unreachable -> BLOCK (no cart can be confirmed).

### F3 Checkout / capture
1. web -> GW -> checkout `POST /carts/{id}/confirm` (re-runs F2 steps 3-4 inside the call; mandate state may have changed).
2. checkout writes order(PENDING, request_id persisted) then -> paypal-adapter create order with `custom_id=mandate_id`, `invoice_id=order_id`, same PayPal-Request-Id on retry (V: replay returns same order).
3. Buyer approves on PayPal sandbox page (real click, V); redirect to return_url on web -> GW -> checkout `/orders/{id}/capture`.
4. checkout re-checks mandate not revoked, then adapter capture. Success -> store capture_id, compute "Protected until day X" (demo window, not PayPal's), emit `order.captured`.
5. Capture result unknown/timeout -> order state CAPTURE_UNKNOWN -> reconcile via adapter get_order (never blind recapture).
6. If mandate revoked between approval and capture: do not capture; order -> CANCELLED_REVOKED (approved-but-uncaptured orders simply expire in PayPal).

### F4 Late-order detection -> triage -> offer -> refund
1. Merchant adds tracking: web -> GW -> tracking `POST /shipments` (+ adapter add_tracking as a "tracking added" signal, V; PayPal cannot hold late/lost state).
2. Demo operator advances the clock (tracking `/demo/clock/advance`) or detector runs on schedule/cron: late/lost shipment -> emit `shipment.late_detected` (idempotent per shipment+kind).
3. resolution consumes event -> opens case (PROBLEM_DETECTED, unique key order_id+kind so duplicates are no-ops). Buyer-reported problems enter via `POST /cases/report` instead (free text untrusted).
4. resolution -> triage-ai `/classify` (text only, no tools). Output enum + confidence; schema fail/low confidence/timeout -> HUMAN_REVIEW. Detector-originated cases skip text classification (kind is already known: LATE/LOST); triage-ai still drafts the message (regex gate).
5. Deterministic policy engine (3 rules) against mandate terms + order facts -> decision: INSIDE_TERMS -> create offer (OFFERED) | OUTSIDE_TERMS -> needs fresh buyer approval link (single-use, bound by proposal_hash) | HUMAN_REVIEW.
6. Buyer accepts offer (or approval link). Case APPROVED.
7. Refund saga (see section 6): 9 ordered checks -> persist refund_attempt(request_id) -> adapter refund -> COMPLETED | UNKNOWN->reconcile | FAILED. Emit `refund.*`, case RESOLVED_REFUNDED.
8. Merchant override: creates a NEW offer requiring buyer approval; never mutates the old one.

### F5 Revoke
1. web -> GW -> mandate `POST /mandates/{id}/revoke` (idempotent). Local commit first; emit `mandate.revoked`.
2. Effects: checkout blocks new carts/captures immediately via sync `/evaluate` (authoritative check at use time, not event-dependent). resolution pauses un-executed offers, but already-promised protection terms for already-captured orders remain per mandate (decision recorded in mandate terms: revocation stops FUTURE spend; protection for completed purchases stands. I - needs PM confirmation).
3. Because enforcement uses sync reads of mandate state, event delay cannot cause a post-revoke spend. Events are for cleanup and audit only.

## 5. Failure modes and fail-closed rules
| failure | behavior |
|---|---|
| mandate down | no cart confirm, no capture; refunds under existing terms wait (queued case), never assumed allowed |
| catalog down | cannot re-price -> block |
| LLM down / bad JSON | shopping: manual cart; intent-fit: NEEDS_BUYER_CONFIRMATION; triage: HUMAN_REVIEW |
| paypal-adapter down | no order/refund; cases stay APPROVED; saga resumes via reconcile job |
| PayPal 409 / timeout on refund | refund_attempt = UNKNOWN; GET refund / capture lookup to reconcile; never new Request-Id for the same intent |
| PayPal 422 over-refund / duplicate invoice | FAILED, to HUMAN_REVIEW (V behaviors) |
| tracking duplicate/missed runs | detector idempotent; missed run is caught next run; unique case key |
| audit down | producers keep events in outbox, relay retries; money path does not block on audit availability (honest trade-off: audit is eventually consistent) |
| gateway token/JWKS unavailable | services reject (deny by default) |
| service cold start (free tier sleep) | callers use timeouts + retries with backoff on idempotent calls; Profile B and warm-up exist to avoid this in demo |
| clock skew / demo clock | only tracking owns time; others ask it or receive timestamps in events |
Rules: (R1) any unparseable or schema-failed AI output = restrictive default; (R2) any authorization dependency unreachable = deny; (R3) no retry of non-idempotent money calls without the persisted Request-Id; (R4) money state transitions are written locally BEFORE the external call.

## 6. Consistency strategy (kept minimal)
- Per-service local ACID transactions. No distributed transactions.
- Transactional outbox: each event-producing service writes event row in same transaction as state change; a relay loop (in-process background task + `/internal/outbox/flush` for cron) delivers.
- Delivery: at-least-once, ordered per aggregate best-effort; consumers dedupe by `event_id` (inbox table or unique key) and treat events as facts not commands.
- Idempotency keys: HTTP `Idempotency-Key` on every mutating public call (stored in checkout/mandate/resolution); PayPal `PayPal-Request-Id` generated by caller, persisted before calling (V basis).
- Only one saga: refund (resolution orchestrates, orchestration-style not choreography). States: REQUESTED -> SENT -> COMPLETED | UNKNOWN -> (reconcile) COMPLETED|FAILED. No compensation needed (refund is the compensation). Order create/capture is a mini state machine in checkout, no saga.
- Reads across services at decision time are synchronous and authoritative (mandate state, capture facts), not from event-built replicas. This removes stale-copy bugs at the cost of coupling and more cold-start exposure (mitigated by Profile B).
- Reconcile job: resolution `POST /refunds/reconcile` + checkout capture reconcile, both safe to call repeatedly.

## 7. Contracts and event transport
- Sync: OpenAPI 3.1 generated by FastAPI per service, committed to `contracts/openapi/<svc>.json`; a CI check fails if code and committed spec diverge. Generated typed clients per consumer (`libs/clients`).
- Events: JSON Schema in `contracts/events/<name>.v1.json`; envelope `{event_id, type, version, occurred_at, producer, aggregate_id, trace_id, payload}`; additive-only changes within a version.
- Transport options:
  - Option 1 Postgres LISTEN/NOTIFY: needs persistent connections; breaks with serverless poolers and across separate free DB projects; services sleep so listeners die. Rejected as primary.
  - Option 2 free broker (Redis/Upstash, NATS, CloudAMQP free tiers, I): extra vendor, extra credentials, extra cold/limit risk, little benefit at demo volume (<100s of events).
  - Option 3 (CHOSEN) Postgres outbox + HTTP push to subscriber `POST /internal/events` (HMAC-signed with internal token), with retry/backoff in the relay and a pull endpoint `GET /internal/outbox?after=seq` for catch-up when a consumer wakes. Sleeping consumers are woken by the push itself (cold start absorbed by retry). Zero new vendors; same mechanism works in Profile B (in-process dispatch when the subscriber is co-located, HTTP otherwise).
- Cost of the choice: no replay history beyond outbox retention, no fan-out management UI, at-least-once only. Acceptable for a demo; revisit with a broker if >1 consumer needs independent replay.

## 8. Deployment profiles
Shared rule: each service is a self-contained FastAPI app with its own `app/` package; a process "host" file mounts one or more of them. Inter-service clients take a base URL OR an in-process ASGI transport via config, so moving between profiles is config, not code.

### Profile A: every service separately deployed
- 10 backend processes + web. Pros: true microservice story, independent failure, matches repo. Cons: on free tiers each idle service sleeps (typical ~15 min idle, ~30-60 s cold start, I); the sync chain gateway -> checkout -> catalog+mandate+adapter can hit several cold starts in one click = timeouts/flake; many projects/secrets to manage; free-tier hours/quotas multiply (I).
- Use for: local `docker compose up` (always), CI contract tests, and optionally a one-time hosted rehearsal.

### Profile B: demo-hardened co-location (same code boundaries)
| process | contains | why grouped |
|---|---|---|
| `edge` | api-gateway (+ serves/proxies web if host allows; else web is static on Vercel/CDN) | single warm entry |
| `core` | mandate, catalog, checkout, tracking, resolution, audit | everything on the sync critical path in one warm process; in-process calls, no cold hops |
| `ai` | shopping-agent, triage-ai | LLM keys isolated; slow calls do not block core workers |
| `paypal` | paypal-adapter (+ MCP) | keeps the only PayPal secret in its own process/env |
| `web` | static/Next.js on Vercel | independent, CDN-warm |
- Each process keeps separate schemas, separate DB roles, separate routers and internal-token audience checks even when in-process (so boundary violations are still caught by tests and by Profile A).
- 4 backend processes + web: 4 cold starts max instead of 10; add an external keep-alive ping (free cron/uptime pinger, I) plus a `scripts/warmup` run before recording and before judges' windows.
- What is given up: independent scaling/restart of co-located services; a crash in `core` takes down six services (acceptable for demo; mitigated by process supervisor restarts).

### Recommendation
- Hackathon demo and the public hosted link: Profile B. Reason: the 3-minute video and judges' ad-hoc visits must not hit cold-start timeouts; sandbox PayPal already needs a real click, so we cannot afford more flake.
- Keep Profile A fully runnable via docker compose and documented as the target topology; state this honestly in the README and video ("same services, co-located for the free tier"). Never claim Profile B is independently scaled.
- Honest microservice trade-off: for a team of AI agents on a ~33-day horizon, microservices add contract, auth, and operational cost with limited functional benefit; we accept it because the user requires it, it makes the credential/LLM isolation boundaries real and reviewable, and Profile B contains the operational risk.

## 9. Observability (minimal)
- `X-Request-Id`/`trace_id` generated at GW, propagated, included in events and audit entries.
- JSON logs with service, trace_id, event_id. `/healthz` (liveness) and `/readyz` (DB + dependency flags) per service. No paid APM.

## 10. Open items
- Re-verify free-tier limits (hosting, Postgres, LLM) before ADR-004/005 final (all I).
- PM to confirm revoke semantics for already-captured orders (F5).
- Real return URL into our server and refund PENDING untested (brief section 3).
