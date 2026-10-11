# checkout: sprint tasks

Labels V/VC/I. Window: 2026-10-10 to 2026-11-10 (submit target; hackathon deadline 2026-11-12 noon PT, VC). Sprints align with threat-model s9 gates. Each task has an owner type (AI coding agent + human review) and lists its test (T) and deploy (D) task. Effort sizes not estimated (build volume is not the constraint; review/testing/sandbox time is).

| Sprint | Dates |
|---|---|
| W1 | Oct 10 - Oct 16 |
| W2 | Oct 17 - Oct 23 |
| W3 | Oct 24 - Oct 30 |
| W4 | Oct 31 - Nov 10 (feature freeze Nov 3, I; remainder = hardening, rehearsal, video, buffer) |

## Week 1 (Oct 10-16): skeleton, schema, return-URL spike
| ID | Task | Test | Deploy |
|---|---|---|---|
| CO-S1-01 | FastAPI app skeleton in `services/checkout`, uv workspace, `libs/common` token verify, `/healthz`, `/readyz`, JSON logging with redaction | T: auth matrix tests CO-T70 | D: container builds; mounted in `hosts/core.py`; local compose up |
| CO-S1-02 | Alembic migration: tables in spec s2 with constraints; role `checkout_app` grants | T: constraint tests (unique cart_id, order_id, double capture blocked) | D: migrate on Neon dev DB; confirm grants limited to schema `checkout` |
| CO-S1-03 | Pydantic models + OpenAPI export to `contracts/openapi/checkout.json`; event JSON Schemas | T: contract diff job (CI) | D: CI path-filtered workflow green |
| CO-S1-04 | Fake adapter + fakes for catalog/mandate/agent (test doubles per test-plan s4) | T: fakes self-test | D: used by CI jobs |
| CO-S1-05 | SPIKE: real redirect to our own server: cloudflared tunnel, then hosted Render+Vercel; record `state`/`token`/`PayerID` behavior, cookie behavior, cold-start behavior; check whether return URLs need registration (I) | T: CO-T3A recorded result | D: deploy `core` + Vercel return page stub; note outcome in this folder's README or sprint log; if blocked, decide manual-capture fallback now |
| CO-S1-06 | Spike: capture Request-Id replay and PENDING observability in sandbox (get_order fields, capture status values) | T: dated spike notes | D: none |
| CO-S1-07 | gitleaks pre-commit + CI, `.env.example`, env manifest + forbidden-vars test | T: CO-T71, CO-T72 | D: CI blocks on failure |
| CO-S1-08 | Align conflicts C1-C13 with gateway, mandate, adapter owners (return route POST alias, `committed_minor`, ticket vs callback, audit seq via BFF) | T: contract tests updated | D: none |
Exit gate: skeleton deployed on Profile B, auth tests green, return-URL spike result known (works / fallback chosen).

## Week 2 (Oct 17-23): cart check pipeline and order creation
| ID | Task | Test | Deploy |
|---|---|---|---|
| CO-S2-01 | Catalog client + re-pricing; `PRICE_MISMATCH`; total math in minor units | T: CO-T01..T03, T05, T74 | D: runs against deployed catalog in `core` |
| CO-S2-02 | Mandate `/evaluate` client with `committed_minor`; fail-closed mapping; `cart_checks` persistence | T: CO-T06, T09, T10 | D: staging smoke |
| CO-S2-03 | Intent-fit client (advisory, tighten-only combiner, timeout -> NEEDS_BUYER_CONFIRMATION) + `proposal_hash` | T: CO-T07, T08, T12 | D: smoke against `ai` process (stub OK until agent ready) |
| CO-S2-04 | `POST /carts`, `GET /carts/{id}`; `cart.checked` outbox + relay | T: CO-T11, T64 | D: events reach audit stub |
| CO-S2-05 | `Idempotency-Key` middleware/table | T: CO-T22, T23 | D: none |
| CO-S2-06 | `POST /carts/{id}/confirm`: re-check, order row first, ticket mint, adapter create, `return_bindings`, `order.created` | T: CO-T04, T20, T21, T24..T27 | D: sandbox create order from hosted `core` (needs adapter live) |
| CO-S2-07 | Sandbox S-tier: create order, manual approve click, observe APPROVED | T: CO-T40 partial | D: hosted rehearsal 1 |
Security gate (threat-model S2): T10 (IDOR), T22 (server-derived money fields), T6 for tool args green.

## Week 3 (Oct 24-30): return, capture, receipt, reconcile
| ID | Task | Test | Deploy |
|---|---|---|---|
| CO-S3-01 | `POST /orders/return` with state/token/buyer/mandate checks, re-fetch APPROVED, compare fields | T: CO-T30..T38 | D: hosted via Vercel return page + gateway alias |
| CO-S3-02 | Capture orchestration + ticket + CAS + `captures` + receipt in one txn; `order.captured` | T: CO-T40, T41, T47, T60..T63 | D: sandbox capture from hosted app |
| CO-S3-03 | Revoke handling: pre-capture sync check, `CANCELLED_REVOKED`, `mandate.revoked` inbox | T: CO-T42..T46 | D: staging revoke drill |
| CO-S3-04 | Failure states: CAPTURE_UNKNOWN, FAILED, PENDING path, `MONEY_DISABLED` | T: CO-T50..T58 | D: fault-injection run in compose |
| CO-S3-05 | Reconcile job + scheduled call (`/internal/reconcile`, `/internal/outbox/flush`) via GitHub Actions or pinger | T: reconcile idempotency tests | D: schedule enabled; bounded rate |
| CO-S3-06 | `GET /orders`, merchant minimal view; receipt endpoint; BFF contract for `audit.seq` | T: C tier + IDOR | D: web integration |
| CO-S3-07 | CI side-by-side jobs (profile-a vs profile-b) | T: CI job itself | D: required checks on main |
| CO-S3-08 | Resolve spike outcomes: update docs (PENDING observed or still unverified; return flow verified or fallback) | T: doc review | D: none |
Exit gate: full golden path in hosted sandbox with real approve click; double-capture and post-revoke properties tested.

## Week 4 (Oct 31-Nov 10): hardening, rehearsal, freeze
| ID | Task | Test | Deploy |
|---|---|---|---|
| CO-S4-01 | Full P0 suite green on both profiles; fix flakes | T: all P0 | D: tag release candidate |
| CO-S4-02 | Chaos run: kill `core` mid-CAPTURING, adapter down, cold start on redirect | T: CO-T58 plus manual drill | D: recorded results |
| CO-S4-03 | Warm-up script path for checkout (dry run to order create) | T: script exit codes | D: `scripts/warmup` used before recording |
| CO-S4-04 | Honest-claims lint on receipt/UI strings; disclosures review | T: CO-T63 | D: none |
| CO-S4-05 | Three hosted rehearsals from the public URL; log each outcome | T: E tier | D: fix-forward only; rollback SHA noted |
| CO-S4-06 | Rollback drill (previous SHA + reconcile); freeze migrations | T: rollback checklist | D: executed once |
| CO-S4-07 | Final gitleaks on history, dependency audit, key rotation per plan; re-verify free-tier limits (Nov 1 reminder) | T: CO-T72 | D: secrets rotated in platform env |
| CO-S4-08 | Demo support: fixed demo mandate/cart seed, US buyer account check, backup recorded segment | T: dry run | D: ready by Nov 8 |
Exit gate: definition of done (test-plan s5) complete; code freeze Nov 3 except bug fixes; Nov 8-10 buffer for video/submission only.

## Cut line and priorities
Must ship (above the line, P0):
- Cart check pipeline with fail-closed behavior and reasons.
- Order create with persisted Request-Id and custom_id/invoice_id binding.
- Return handling with bound `state` + re-fetch + mandate re-check + capture + receipt.
- Revoke-before-capture handling; capture UNKNOWN reconcile.
- Receipt with checks, advisory intent-fit, mandate hash, audit event id, remaining cap, demo-window label.

Cut first (in order, if schedule slips):
1. Webhook hint (REQ-CO-025) - never build.
2. Buyer cancel flow `POST /orders/cancel` (REQ-CO-024).
3. PENDING polling beyond the simple state + manual reviewer visibility (REQ-CO-020 simplified: mark and stop).
4. Merchant-scoped `GET /orders` filters beyond captured list; pagination niceties.
5. Cumulative-cap accounting (REQ-CO-022): fall back to per-order cap check only, state it in the demo.
6. Side-by-side CI job: keep Profile A check as a nightly instead of a PR gate.
7. Intent-fit integration polish (it degrades to NEEDS_BUYER_CONFIRMATION anyway).
Never cut: fail-closed checks, server-derived amounts, state binding, double-capture guard, secrets hygiene, honest labels.

Fallback if the return redirect cannot be made reliable on free hosting: demo uses the manual "I approved at PayPal, continue" button calling `POST /orders/{id}/capture` (same verification); say so honestly in the video notes.

## Dependencies to track
- mandate: `/evaluate` accepts `committed_minor`; `GET /mandates/{id}` returns hash, terms, window_days.
- catalog: `/prices/resolve` returns merchant_id, unit_minor, currency.
- shopping-agent: `/intent-fit` contract.
- paypal-adapter: DTOs for get_order/get_capture; ticket verification; 409 -> UNKNOWN envelope.
- api-gateway: `/orders/paypal/return` POST alias, same-site proxy decision, BFF audit seq fill.
- web: return page route with retry; warm-up call before approve click.
