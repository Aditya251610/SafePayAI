# checkout: PRD

Labels: V verified (our 2026-10-10 sandbox spike), VC vendor claim, I inference/unverified. No secrets here. Source of truth on conflicts: `architecture/service-map.md`, `architecture/adr.md`; deltas recorded in `spec.md` section 12.

## 1. Purpose
- Single owner of cart -> check -> order -> capture -> receipt (service-map).
- Turns a buyer-signed Mandate plus a server-priced cart into one PayPal sandbox purchase, and proves why it was allowed.
- Server derives merchant, amount, currency, capture_id. Client and model values are ignored.
- Python 3.12 / FastAPI / Pydantic v2 / SQLAlchemy 2 (ADR-002). Schema `checkout` in the shared Postgres (ADR-004).

## 2. Users and use
| Actor | Need |
|---|---|
| Buyer | Pay inside the mandate; see reasons for allow/block; see receipt with "Protected until day X" |
| Merchant (shared demo login, disclosed) | See captured orders so tracking can be added |
| Reviewer / judge | Inspect checks list, hashes, audit link |
| tracking, resolution (services) | Read order, capture facts, promise date; consume `order.captured` |

## 3. Requirements
Priority: P0 = demo cannot work without; P1 = should; P2 = cut first.

| ID | P | Requirement | Label / basis |
|---|---|---|---|
| REQ-CO-001 | P0 | `POST /carts` accepts only `{mandate_id, lines[{sku, qty}]}` (+ optional agent-stated prices, ignored for money); re-prices every line via catalog `/prices/resolve` | brief s2 step 2, P2 principle |
| REQ-CO-002 | P0 | Run mandate `/evaluate` with the server-priced cart; store every check result (name, pass/fail, reason code) in `cart_checks`; any hard block = cart cannot be confirmed | service-map |
| REQ-CO-003 | P0 | Mandate, catalog, or evaluate unreachable/timeout = BLOCK (fail closed) | overview F2 |
| REQ-CO-004 | P0 | Call shopping-agent `/intent-fit` only if zero hard blocks. Result may only tighten (PASS / NEEDS_BUYER_CONFIRMATION / REJECT_WITH_REASON). Timeout/error = NEEDS_BUYER_CONFIRMATION. Never clears a hard block | brief s2 step 3 |
| REQ-CO-005 | P0 | `POST /carts/{id}/confirm` re-runs re-pricing and evaluate inside the call (state may have changed), verifies `proposal_hash`, requires buyer confirmation when intent-fit = NEEDS_BUYER_CONFIRMATION | overview F3 step 1 |
| REQ-CO-006 | P0 | Create the PayPal order via paypal-adapter with `custom_id = mandate_id`, `invoice_id = order_id`, a persisted PayPal-Request-Id, and an `authorization_ticket` | V: custom_id/invoice_id survive to capture; V: Request-Id replay returns same order |
| REQ-CO-007 | P0 | Write the order row (state CREATING, request_id) locally BEFORE the external call (R4) | overview s5 |
| REQ-CO-008 | P0 | Build return_url/cancel_url server-side with a bound random `state`; never accept client URLs | auth-gateway s5 |
| REQ-CO-009 | P0 | Return handler checks: state valid/unexpired/unused, buyer matches binding, `token` == stored paypal_order_id, mandate still active; PayerID opaque | auth-gateway s5 |
| REQ-CO-010 | P0 | Before capture: re-fetch order from PayPal (via adapter), require status APPROVED, compare amount/currency/custom_id/invoice_id to DB, re-check mandate (sync), then capture with persisted request_id | V: APPROVED then capture 201 COMPLETED |
| REQ-CO-011 | P0 | Mandate revoked/expired between approval and capture: do NOT capture; order -> CANCELLED_REVOKED; emit `order.capture_failed` (reason REVOKED); audit | overview F3.6 |
| REQ-CO-012 | P0 | Capture result unknown/timeout -> CAPTURE_UNKNOWN -> reconcile via get_order/get_capture; never blind recapture | overview s5 R3 |
| REQ-CO-013 | P0 | Store capture (capture_id, amount, currency, custom_id, invoice_id) and emit `order.captured` only after PayPal reports COMPLETED | V |
| REQ-CO-014 | P0 | Receipt: checks list with reasons, intent-fit verdict labelled ADVISORY, mandate hash, audit seq/event id, remaining cap, "Protected until day X" (demo value, not PayPal's window) | brief s2 step 4 |
| REQ-CO-015 | P0 | `Idempotency-Key` required on every mutating public call; same key + same body replays the stored response; same key + different body = 422 | overview s6 |
| REQ-CO-016 | P0 | Consume `mandate.revoked`: mark un-captured carts/orders blocked. Authority is still the sync check at use time; event is cleanup only | overview F5 |
| REQ-CO-017 | P0 | Emit `cart.checked`, `order.created`, `order.captured`, `order.capture_failed` via transactional outbox (ADR-003) | service-map |
| REQ-CO-018 | P1 | Reconcile job `POST /internal/reconcile`: re-reads CREATING/AWAITING/CAPTURING/CAPTURE_UNKNOWN/CAPTURE_PENDING orders from PayPal; safe to call repeatedly | overview s6 |
| REQ-CO-019 | P1 | Duplicate return / page refresh returns the existing result (no second capture) | auth-gateway s5 |
| REQ-CO-020 | P1 | Capture `PENDING` handled without claiming payment success (UNVERIFIED behavior, I) | brief s3 untested |
| REQ-CO-021 | P1 | `GET /orders?mandate_id=` for resolution/tracking/web; merchant sees captured orders (minimal fields) | service-map + delta |
| REQ-CO-022 | P1 | Remaining cap = mandate cap minus committed spend of this mandate, shown on cart and receipt | brief s2 |
| REQ-CO-023 | P1 | Structured JSON logs with request_id/trace_id; `/healthz`, `/readyz` | overview s9 |
| REQ-CO-024 | P2 | Buyer-initiated cancel via cancel_url marks order CANCELLED_BUYER | I |
| REQ-CO-025 | P2 | Optional PayPal webhook as a hint to trigger reconcile (never trusted) | untested, I |

## 4. Non-goals
- Refunds, carrier status, tracking logic, case handling (resolution/tracking).
- Holding PayPal credentials or calling an LLM directly (shopping-agent does; adapter holds creds).
- Recommending items, pricing authority (catalog), mandate rules (mandate).
- Inventory, shipping rate quotes, tax, multi-currency (USD only, I), multi-merchant split orders (3 virtual merchants settle to one sandbox merchant, brief).
- Fastlane, Vault v3, Agent Ready, Store Sync, WebMCP, production Payouts (gated).
- Claims: PayPal-backed/verified/protected, legally binding, non-repudiable, real money.

## 5. Metrics (no invented numbers; thresholds only where the docs give them)
| Metric | Definition | Target |
|---|---|---|
| Mismatched captures | captures whose amount/currency/custom_id differ from DB | 0 (property, tested) |
| Post-revoke captures | captures started after mandate revoke committed | 0 (property, tested) |
| Double captures per order | >1 capture row per order | 0 |
| Hard-block escapes | orders created for carts with a hard block | 0 |
| Golden path | mandate -> cart -> order -> approve -> capture -> receipt end to end in hosted sandbox | passes in CI-run rehearsal and 3 hosted rehearsals before Nov 10 (I, team choice) |
| Reconcile coverage | orders left in non-terminal state after reconcile run | 0 except PENDING cases |
| Agent cart validity | reported by shopping-agent doc: target >= 95% valid (brief); checkout only consumes it | owned by shopping-agent |
| Latency, cold-start | measured in week 1 on Profile B; no target until measured | unknown |

## 6. Risks
| # | Risk | Likelihood / impact | Mitigation |
|---|---|---|---|
| R1 | Real return URL into our own server is UNTESTED (I) | Med / High | Week-1 spike with cloudflared tunnel then Render+Vercel; keep `POST /orders/{id}/capture` manual fallback and UI "I approved, continue" |
| R2 | Capture returns PENDING (UNVERIFIED) | Low-Med / Med | CAPTURE_PENDING state, poll, no receipt "Protected" until COMPLETED; if sandbox never yields it, keep code path tested with a fake adapter only |
| R3 | Cold start during redirect (Render ~1 min wake, V) | High / High | Profile B, return page static on Vercel with retry, warm-up before approve click |
| R4 | Cookie lost on cross-site redirect | Med / Med | Same-site proxy via Vercel rewrite (preferred); else "sign in again" screen, never auto-capture |
| R5 | India-based buyer cannot pay USD (V) | Known | Use US personal sandbox buyer for demo |
| R6 | Capture Request-Id replay semantics not spiked (only order create and refund are V) | Med / Med | Reconcile via get_order first; treat as I |
| R7 | Mandate is pure and has no spend ledger; cumulative cap needs checkout input | Med / Med | Checkout passes `committed_minor`; contract to confirm with mandate owner |
| R8 | Spec drift vs other services (return route, receipt audit seq) | Med / Low | Deltas in spec s12; OpenAPI committed in `contracts/openapi/checkout.json`, CI diff |
| R9 | AI-written code leaks secrets into a public repo | Med / High | gitleaks pre-commit + CI; env names only |
| R10 | Revoke vs already-captured protection semantics — **confirmed (D1, 00-platform-prd.md)** | Med / Low | Checkout only stops FUTURE spend; already-earned protection stands; semantics owned by mandate/resolution |

## 7. Demo role (honesty)
- Show reasons: each check pass/fail on screen; intent-fit labelled "advisory".
- Show "Protected until day X" as a demo value from the mandate's pre-authorized terms, labelled "demo window, not PayPal's".
- Sandbox banner and SIMULATED CARRIER banner owned by web; checkout never states "PayPal protected".
