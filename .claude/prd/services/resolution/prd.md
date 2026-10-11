# resolution: PRD

Date: 2026-10-10. Labels: V verified, VC vendor claim, I inference/unverified. No invented numbers; "unset" = a config value the team must choose.
Service-map and adr.md win on conflicts (see spec.md section 15). Stack: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic (ADR-002).

## 1. Purpose
`resolution` is the decision point of the SafePayAI loop. It receives a problem signal (late/lost from `tracking`, or buyer free text), runs the case state machine, applies a deterministic merchant policy against the mandate's pre-authorized terms, issues offers, gates anything outside the terms behind a single-use buyer approval bound by `proposal_hash`, runs 9 ordered pre-refund checks, and orchestrates the single refund saga through `paypal-adapter`. It also owns the human-review queue and in-app notifications.

Principle (non-negotiable): AI never decides money. Triage output is an enum plus confidence and an `injection_suspected` flag; every amount comes from policy + mandate terms + capture facts.

## 2. Users
| user | what they need |
|---|---|
| Buyer | Neutral, quick resolution of a late/lost/problem order; sees reasons; always has a path to a human |
| Merchant (shared demo login, disclosed) | See cases, add reship confirmation, propose an override (never self-approved) |
| Reviewer (self-asserted name, disclosed) | Queue with age + SLA timer, brief, decide a permitted path |
| Operator | Freeze/unfreeze refunds, run reconcile, never a merchant login |
| Judge | Watch an order go late -> offer -> refund with visible reasons, audit, kill switch |

## 3. Requirements
Priority: P0 = demo-blocking/safety, P1 = should ship, P2 = stretch.

| ID | P | Requirement | Label |
|---|---|---|---|
| REQ-RS-001 | P0 | Case lifecycle uses exactly the 12 states PROTECTED, MONITORING, PROBLEM_DETECTED, TRIAGED, OFFERED, HUMAN_REVIEW, APPROVED, REFUNDING, RESOLVED_REFUNDED, RESOLVED_RESHIP, DECLINED, CLOSED; only transitions in spec.md section 3 are legal; every transition writes `case_transitions` | I (design) |
| REQ-RS-002 | P0 | Open a case from `shipment.late_detected` / `shipment.lost_detected` events; duplicates are no-ops (unique `order_id + kind`) | I |
| REQ-RS-003 | P0 | Accept buyer problem text via `POST /cases/report`; text is untrusted, length-capped, stored, never executed; classified only by `triage-ai` | I |
| REQ-RS-004 | P0 | Triage failure, timeout, schema error, confidence below threshold, `injection_suspected`, or category/carrier-fact disagreement route to HUMAN_REVIEW (fail closed) | I |
| REQ-RS-005 | P0 | Policy engine is pure functions (no I/O, no clock, no LLM) implementing 3 hardcoded illustrative policies (refund cap, category exclusions, buyer velocity) plus mandate-terms check; output is a decision class + reasons | I |
| REQ-RS-006 | P0 | Inside mandate pre-authorized terms and passing policy: create offer; execute per pre-authorization tier (spec section 5) | I |
| REQ-RS-007 | P0 | Outside terms: create a proposal and a single-use approval link bound to `proposal_hash`; consent requires the matching authenticated buyer session; any change of amount/terms/capture invalidates the link | I |
| REQ-RS-008 | P0 | Before any refund run the 9 ordered checks (spec section 6); any failure or error blocks (fail closed) and records which check failed | I |
| REQ-RS-009 | P0 | Persist `refund_attempt` with `request_id` and `invoice_id` before calling the adapter; one refund per case (unique constraint); unique `invoice_id` per refund | V (PayPal behaviour) |
| REQ-RS-010 | P0 | Treat PayPal 409 as IN_PROGRESS, timeout/5xx as UNKNOWN; resolve only by lookup/idempotent replay via the adapter, never a new Request-Id; 422 REFUND_AMOUNT_EXCEEDED and DUPLICATE_INVOICE_ID are terminal FAILED -> HUMAN_REVIEW | V |
| REQ-RS-011 | P0 | `REFUNDS_FROZEN` kill switch: absent/unreadable = frozen; blocks offers' execution, approvals, retries, reconcile-triggered sends and the poller; items stay APPROVED, not lost; unfreeze needs operator role + reason; every toggle audited | I (design, threat-model) |
| REQ-RS-012 | P0 | Concurrency safety: double approval, double accept, duplicate events, concurrent reconcile produce exactly one refund (CAS + row locks + unique constraints) | I |
| REQ-RS-013 | P0 | Reconciliation job resolves SENT/UNKNOWN attempts; idempotent; safe to call repeatedly | I |
| REQ-RS-014 | P0 | No auto-deny: system outcomes are only offer, buyer-approval request, or HUMAN_REVIEW; DECLINED is entered only by a human (reviewer) or the buyer declining an offer, with a reason | I (threat-model) |
| REQ-RS-015 | P0 | Protection window holds (auto-extends) while a case is open, so review delay never expires coverage | I (threat-model) |
| REQ-RS-016 | P0 | Merchant override creates a NEW offer/proposal with a new hash; old offer and tokens are SUPERSEDED/revoked; merchant cannot approve it | I |
| REQ-RS-017 | P1 | Human-review queue with age and demo SLA timer; reviewer decisions limited to permitted paths; reviewer cannot trigger a refund directly | I |
| REQ-RS-018 | P1 | In-app notifications (no email) with neutral template wording; banned-word gate on every buyer-visible string; AI drafts pass the regex gate (no URLs/amounts) or fall back to static templates | I |
| REQ-RS-019 | P1 | Outbox events via Postgres transactional outbox, HTTP push, pull catch-up (ADR-003); consumers dedupe | I |
| REQ-RS-020 | P1 | `Idempotency-Key` on every mutating public call | I |
| REQ-RS-021 | P1 | Server derives amount, currency, merchant, capture_id; client-supplied values for these are ignored | I |
| REQ-RS-022 | P1 | RESOLVED_RESHIP path (buyer chooses reship, merchant confirms) | I |
| REQ-RS-023 | P2 | Escalation LATE -> LOST on an open case; per-mandate/per-merchant freeze | I |
| REQ-RS-024 | P1 | Emit domain events for audit (`case.*`, `offer.created`, `approval.granted`, `refund.*`); no PII/secrets in payloads | I |
| REQ-RS-025 | P1 | Health: `/healthz` liveness, `/readyz` (DB + flag readable); structured logs with trace_id | I |

## 4. Non-goals
- No LLM calls from this service (it calls `triage-ai`); no PayPal credentials; no carrier simulation; no price truth.
- No automatic denial of any claim; no fraud scoring or accusation of the buyer.
- No email/SMS/push; in-app notifications only.
- No real disputes/chargebacks integration (Disputes API untested, optional; I).
- No per-merchant policy configuration UI (3 hardcoded illustrative policies).
- No multi-refund per case, no partial-refund negotiation loop in v1 (one refund per case; PayPal itself allows several partials, V, not used).
- No claim of legally binding approvals, non-repudiation, PayPal-backed protection, compliance, fraud-proofing, or a measured SLA.
- Not a general case-management or ticketing system.

## 5. Metrics (illustrative; sandbox/demo data only, no baseline exists, targets unset)
| metric | definition | note |
|---|---|---|
| Time from problem signal to resolution (primary) | `case.opened` occurred_at -> `case.resolved` occurred_at, reported by path (auto-in-terms, buyer-approved, human-reviewed) in both wall-clock and demo-clock | Illustrative only; demo clock is simulated, so wall-clock is what to quote. Target: unset. Contrast with PayPal's manual claim flow (~14 days average, VC/I) is context, not a measured comparison |
| Disputes per order (guardrail) | Sandbox cannot produce real disputes (Disputes API untested, I). Proxy: buyer "reopen/appeal" (DECLINED -> HUMAN_REVIEW) plus `case.opened` per captured order | Illustrative only; must not rise as resolution speeds up |
| Duplicate refunds | Count of cases with >1 PayPal refund | Must be 0 (safety invariant, not a goal metric) |
| Out-of-terms executions without approval | Refunds executed whose `approval_basis` is missing | Must be 0 |
| Unresolved UNKNOWN age | Oldest `refund_attempt` in SENT/UNKNOWN | Watch; unset target |
| Human-review queue age | Oldest HUMAN_REVIEW item vs demo SLA target | Demo target, not a promise |

## 6. Risks
| risk | impact | mitigation |
|---|---|---|
| Double refund via concurrency or retry | Money loss | Unique refund per case + persisted Request-Id + CAS APPROVED->REFUNDING + PayPal 409/422 backstops (V); tests in test-plan |
| Lost response leaves refund id unknown (cannot GET by id) | Stuck UNKNOWN | Adapter replays the identical request (same Request-Id) which returns the original refund (V); needs adapter reconcile op; PayPal Request-Id retention window unknown (I) |
| PayPal refund returns PENDING | State ambiguity | Not tested (I); treat PENDING as IN_PROGRESS and poll |
| Kill switch unreadable | Refunds stop | Intended fail-closed; runbook; visible in `/readyz` |
| Free-tier sleep/cold start in `core` mid-saga | Timeouts | Saga is resumable from persisted state; reconcile job; warm-up script |
| Misclassification by triage | Wrong path | Only a category input; disagreement with carrier DB fact -> HUMAN_REVIEW; amounts never from AI |
| Policy values (cap, velocity) are illustrative | Misread as real | Labelled illustrative in UI and docs |
| Reviewer/merchant identity is self-asserted/shared | No accountability | Disclosed; audit stamps `merchant_shared`, `reviewer_name_selfasserted` |
| Neon pooler breaks session advisory locks | Lost mutual exclusion | Use `pg_advisory_xact_lock` and row locks only (I) |
| Scope creep before day 14 | Demo incomplete | Cut line in sprint-tasks.md |
