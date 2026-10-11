# resolution: technical spec

Labels: V verified (our PayPal sandbox spike, 2026-10-10), VC vendor claim, I inference/design/unverified. Python 3.12, FastAPI, Pydantic v2 (`extra="forbid"`), SQLAlchemy 2, Alembic, httpx.

## 1. Boundaries
- Schema `resolution`, own DB role, no cross-schema SQL (ADR-004). Tables: `cases`, `case_transitions`, `case_signals`, `offers`, `approvals`, `policy_decisions`, `refund_attempts`, `notifications`, `control_flags`, `idempotency_keys`, `outbox`, `inbox_dedupe`.
- Sync calls (downward only): `triage-ai` (/classify, /draft, /brief), `mandate` (terms, status), `checkout` (order/capture facts, protected_until), `tracking` (shipment facts, demo clock), `paypal-adapter` (refund, get_refund, get_capture, reconcile). Never called by those services synchronously; they reach us by event.
- Code layout (hexagonal where it pays; the rest is transaction script):
  - `domain/` pure: `states.py` (transition table), `policy.py`, `proposal.py` (hash), `checks.py` (check functions take facts, return result), `wording.py`. No imports of FastAPI, SQLAlchemy, httpx, clock, random.
  - `app/` use cases: `OpenCase`, `RunTriage`, `Decide`, `AcceptOffer`, `ConsentApproval`, `ExecuteRefund`, `Reconcile`, `ReviewDecision`, `MerchantAction`. Coordinate transactions, ports, outbox.
  - `ports/` (Protocols): `MandatePort`, `CheckoutPort`, `TrackingPort`, `TriagePort`, `AdapterPort`, `ClockPort`, `FlagPort`. `adapters/` implement with httpx or in-process ASGI (config, ADR profile rule).
  - Controllers never call repositories directly (architectural smell per rules).

## 2. Case model
`cases`: `id (uuid)`, `order_id`, `capture_id` (copied from checkout, server-derived), `mandate_id`, `buyer_id`, `kind` (LATE|LOST|DAMAGED|WRONG_ITEM|NOT_AS_DESCRIBED|OTHER), `origin` (DETECTOR|BUYER_REPORT), `state`, `version int` (CAS), `terms_snapshot jsonb` + `terms_hash` (mandate terms copied at open; revocation stops FUTURE spend only, protection for captured orders stays, see conflicts C6), `opened_at`, `window_hold bool`, `amount_minor`, `currency`, `triage jsonb` (category, confidence, injection_suspected, model id; no raw model text drives anything), `untrusted_text` (length-capped), `human_review_reason`, `human_review_entered_at`.
- Unique `(order_id, kind)`. Case materialization is lazy at first signal (section 3 note).
- Money columns are integer minor units; currency ISO code from capture, never client.

## 3. State machine
States (12): PROTECTED, MONITORING, PROBLEM_DETECTED, TRIAGED, OFFERED, HUMAN_REVIEW, APPROVED, REFUNDING, RESOLVED_REFUNDED, RESOLVED_RESHIP, DECLINED, CLOSED.

Lazy materialization: `resolution` does not consume `order.captured` (not in service-map event matrix). On first signal the case row is created and the back-filled transitions PROTECTED -> MONITORING -> PROBLEM_DETECTED are written in one transaction with `actor=system, reason=materialized`. UI shows "Protected/Monitoring" from checkout/tracking data before a case exists (conflict C2).

Legal transitions (everything else raises `IllegalTransition`, HTTP 409 `ILLEGAL_TRANSITION`):

| # | from | to | trigger | actor | guard |
|---|---|---|---|---|---|
| T1 | PROTECTED | MONITORING | shipment exists (materialization) | system | |
| T2 | PROTECTED | PROBLEM_DETECTED | buyer report with no shipment, or lost/late signal | system/buyer | |
| T3 | MONITORING | PROBLEM_DETECTED | late/lost signal or buyer report | system/buyer | `(order_id,kind)` unique |
| T4 | MONITORING | CLOSED | delivered and protection window ended without problem | system | only via tracking fact; no case row unless a signal existed, so effectively unused in v1 (kept for completeness) |
| T5 | PROBLEM_DETECTED | TRIAGED | triage ok (valid enum, confidence >= `PS_RESOLUTION_TRIAGE_MIN_CONFIDENCE`, no injection flag) or detector origin (kind known) | system | |
| T6 | PROBLEM_DETECTED | HUMAN_REVIEW | triage failure/timeout/low confidence/injection flag/kind-vs-carrier disagreement | system | fail closed |
| T7 | TRIAGED | OFFERED | policy class INSIDE_TERMS or OUTSIDE_TERMS | system | offer/proposal persisted |
| T8 | TRIAGED | HUMAN_REVIEW | policy class HUMAN_REVIEW | system | |
| T9 | OFFERED | APPROVED | buyer accepts INSIDE_TERMS offer, or consents via approval link, or pre-authorization auto-accept (tier 0) | buyer / mandate_preauth | offer ACTIVE, hash match, freeze irrelevant here (freeze blocks execution, not approval) |
| T10 | OFFERED | RESOLVED_RESHIP | buyer chose RESHIP offer and merchant confirms reship | buyer then merchant | RESHIP offers only |
| T11 | OFFERED | DECLINED | buyer declines the offer | buyer | reason code from enum |
| T12 | OFFERED | HUMAN_REVIEW | offer/link expired, or merchant override requested review, or facts changed (hash mismatch on re-issue) | system | no auto-deny, window held |
| T13 | HUMAN_REVIEW | OFFERED | reviewer decision creates an offer/proposal (never a direct refund) | reviewer | permitted paths only |
| T14 | HUMAN_REVIEW | DECLINED | reviewer declines with written reason | reviewer | reason mandatory, audited |
| T15 | HUMAN_REVIEW | CLOSED | reviewer closes (duplicate/delivered/buyer withdrew) | reviewer | reason mandatory |
| T16 | APPROVED | REFUNDING | all 9 checks pass; CAS | system | single winner |
| T17 | APPROVED | HUMAN_REVIEW | a check fails for a non-transient reason (e.g. package now delivered, amount exceeds remaining) | system | records failed check |
| T18 | REFUNDING | RESOLVED_REFUNDED | attempt COMPLETED (reconciled or direct) | system | PayPal COMPLETED |
| T19 | REFUNDING | HUMAN_REVIEW | attempt FAILED (422 REFUND_AMOUNT_EXCEEDED, DUPLICATE_INVOICE_ID, adapter reject) or reconcile retries exhausted | system | |
| T20 | REFUNDING | APPROVED | adapter confirms NOT SENT (frozen, pre-flight reject) | system | attempt marked NOT_SENT; no PayPal call occurred |
| T21 | RESOLVED_REFUNDED | CLOSED | notification sent, grace over | system | |
| T22 | RESOLVED_RESHIP | CLOSED | same | system | |
| T23 | DECLINED | CLOSED | after appeal window | system | |
| T24 | DECLINED | HUMAN_REVIEW | buyer appeals (buyer can always reach a human) | buyer | |
| T25 | DECLINED | OFFERED | merchant override (NEW offer, buyer approval needed) | merchant | creates new proposal/hash |
| T26 | OFFERED | OFFERED | merchant override supersedes active offer | merchant | old offer SUPERSEDED, tokens revoked, `version` bumps |
| T27 | HUMAN_REVIEW | HUMAN_REVIEW | kind escalation LATE->LOST or new evidence | system | audit only (P2) |

Notes:
- REFUNDING with attempt SENT/UNKNOWN stays REFUNDING until reconcile decides; no other exit.
- RESOLVED_*/CLOSED are terminal for money; nothing leaves them. DECLINED -> CLOSED is the only terminal exit besides appeal/override.
- There is no system-driven transition into DECLINED (REQ-RS-014).
- Every transition: `UPDATE cases SET state=:to, version=version+1 WHERE id=:id AND state=:from AND version=:v`; rowcount 0 -> reload, `ConcurrentModification` (409). Transition + `case_transitions` row + outbox row in ONE transaction.
- Property: the transition table is data (`dict[State, set[State]]`) and the only mutation path is `apply_transition()`.

## 4. Policy engine (pure functions)
Signature (no I/O, no clock, no randomness):
```
decide(facts: DecisionFacts, cfg: PolicyConfig) -> Decision
Decision = {klass: INSIDE_TERMS | OUTSIDE_TERMS | HUMAN_REVIEW, reasons: [Reason], amount_minor, currency, policy_version}
```
`DecisionFacts` (assembled by a use case from fresh sync reads, then frozen): kind, triage_ok, confidence, injection_suspected, carrier_status/carrier_agrees, terms_snapshot (kinds covered, max_refund_minor, window), mandate_hash_valid, protected_until, case_opened_at, now (passed in), capture (status, amount, refunded_total, currency), item_categories, buyer_refunds_last_window (count from own `refund_attempts` COMPLETED, demo clock).

Three hardcoded ILLUSTRATIVE policies (labelled illustrative in UI/docs; values from config, `PS_RESOLUTION_POLICY_VERSION` pinned on every decision):
| id | rule | on hit |
|---|---|---|
| P1 refund cap | amount_minor > `PS_RESOLUTION_POLICY_REFUND_CAP_MINOR` (brief: ~USD 50, illustrative) | HUMAN_REVIEW |
| P2 category exclusion | any item category in `PS_RESOLUTION_POLICY_EXCLUDED_CATEGORIES` | HUMAN_REVIEW |
| P3 buyer velocity | completed refunds for buyer in last `PS_RESOLUTION_POLICY_VELOCITY_WINDOW_DAYS` (brief: 30) > `PS_RESOLUTION_POLICY_VELOCITY_MAX` (brief: 2) | HUMAN_REVIEW |

Amount derivation (server only): `amount_minor = capture.amount - capture.refunded_total` for the whole order in v1 (full-order rule); currency = capture currency. A mandate whose terms declare a different rule is not supported in v1 and falls to HUMAN_REVIEW with reason `UNSUPPORTED_TERMS`.

Decision table, first matching row wins (top to bottom). Any missing/errored fact = HUMAN_REVIEW (fail closed):
| # | condition | class | reason code |
|---|---|---|---|
| D0 | any required fact missing, stale, or errored; mandate HMAC/hash invalid | HUMAN_REVIEW | FACT_UNAVAILABLE / TERMS_INVALID |
| D1 | triage not ok, confidence < `PS_RESOLUTION_TRIAGE_MIN_CONFIDENCE`, or injection_suspected | HUMAN_REVIEW | TRIAGE_FAIL_CLOSED |
| D2 | kind = OTHER | HUMAN_REVIEW | KIND_OTHER |
| D3 | kind claims LATE/LOST but carrier fact in OUR DB disagrees (e.g. delivered on time) | HUMAN_REVIEW | CARRIER_DISAGREES |
| D4 | P2 category excluded | HUMAN_REVIEW | POLICY_CATEGORY |
| D5 | P3 velocity exceeded | HUMAN_REVIEW | POLICY_VELOCITY |
| D6 | P1 amount over cap | HUMAN_REVIEW | POLICY_CAP |
| D7 | kind in (DAMAGED, WRONG_ITEM, NOT_AS_DESCRIBED) | HUMAN_REVIEW | NEEDS_EVIDENCE (reviewer may then propose; buyer approval still required) |
| D8 | kind in (LATE, LOST), kind covered by terms, amount <= terms.max_refund_minor, case_opened_at <= protected_until | INSIDE_TERMS | IN_TERMS |
| D9 | kind in (LATE, LOST), amount > terms.max_refund_minor (still <= policy cap) OR kind not covered by terms OR outside window | OUTSIDE_TERMS | OUT_OF_TERMS_<which> |
| D10 | otherwise | HUMAN_REVIEW | DEFAULT_DENY_TO_HUMAN |

Outcomes never include a denial. Same inputs always give the same Decision (property test). Each Decision is stored in `policy_decisions` with the full facts hash.

Merchant override decisions use class `MERCHANT_OVERRIDE`: P1-P3 and terms are bypassed by the merchant's choice, but hard stops (freeze, remaining refundable, currency, capture match, buyer approval) are not.

## 5. Mandate pre-authorization tiering
Pre-authorization means "the buyer, when signing the mandate, pre-agreed this protection term". It is demo-grade server attestation, not a buyer-held signature, not legally binding (honesty rule).

| tier | when | buyer action at claim time | execution |
|---|---|---|---|
| 0 AUTO | INSIDE_TERMS and `PS_RESOLUTION_PREAUTH_AUTO_EXECUTE=true` | none (notified) | offer created and auto-accepted in the same transaction (T7+T9, `approval_basis=MANDATE_PREAUTH`), then checks, then refund |
| 1 CONFIRM | INSIDE_TERMS and auto off, or offer includes RESHIP choice | one authenticated click `POST /offers/{id}/accept` | T9 on accept |
| 2 APPROVE | OUTSIDE_TERMS, reviewer-created proposal, merchant override | single-use link bound to `proposal_hash` + matching buyer session + fresh CSRF nonce (auth-gateway 4.2) | T9 on consent |
| 3 REVIEW | HUMAN_REVIEW | reviewer chooses permitted path (creates an offer -> tier 1/2) | reviewer cannot execute a refund |

`proposal_hash = SHA-256(JCS-canonical{case_id, order_id, capture_id, mandate_id, terms_hash, policy_version, action (REFUND|RESHIP), amount_minor, currency, offer_seq})`. Recomputed from DB at consent and again as check #2 at execution; mismatch rejects.

Approval link (token format per auth-gateway 4.2): `approvals` row stores `sha256(token)`, `tid`, `proposal_hash`, status issued|redeemed|expired|revoked. Redeem: constant-time HMAC check -> recompute hash -> `UPDATE approvals SET status='redeemed' WHERE tid=:t AND status='issued' AND exp>:now` (rowcount 1 wins) -> require session buyer_id == `cases.buyer_id`. Replay -> 409 `APPROVAL_REPLAY` + audit. TTL `PS_RESOLUTION_APPROVAL_LINK_TTL_S` (24 h default I). Expired -> T12 to HUMAN_REVIEW (not deny). Links are inserted by server template only; AI-drafted text cannot carry URLs.

## 6. The 9 ordered pre-refund checks (fail closed)
Run in a single function `run_checks(facts) -> CheckReport` that stops at the first failure, writes every result to `policy_decisions.checks jsonb`, and treats ANY exception or unreachable dependency as FAIL. Facts are re-read fresh (not from case snapshot) except terms hash. Order matters (cheap/global first, money-adjacent last).

| # | check | pass condition | on fail |
|---|---|---|---|
| 1 | Kill switch | `REFUNDS_FROZEN` readable AND false (absent/unreadable = frozen). Per-mandate/merchant freeze if present | stay APPROVED, no attempt row, `refund.blocked_frozen` (no state change); retry on unfreeze |
| 2 | Authorization valid | case APPROVED; approval basis present (preauth, accepted offer, or redeemed approval); recomputed `proposal_hash` == stored; offer ACTIVE (not superseded) | T17 HUMAN_REVIEW |
| 3 | Terms integrity | mandate service returns terms whose hash == `terms_hash` and HMAC valid; policy_version equals decision's | HUMAN_REVIEW |
| 4 | Capture identity | adapter/checkout `get_capture`: capture_id matches order, `custom_id` == mandate_id (V survives), status COMPLETED or PARTIALLY_REFUNDED, currency equals proposal currency | HUMAN_REVIEW |
| 5 | Amount bounds | integer > 0; == proposal amount; <= remaining refundable (capture amount - refunded); <= `terms.max_refund_minor` unless approval basis is explicit buyer approval/override; <= adapter per-call ceiling | HUMAN_REVIEW |
| 6 | Policy re-evaluation | pure `decide()` on fresh facts yields same class (or MERCHANT_OVERRIDE basis); `policy_version` unchanged | HUMAN_REVIEW |
| 7 | No prior money action | no `refund_attempts` row for this case, none in-flight/COMPLETED for this order (v1 one refund per order, partial unique index) | if own attempt exists: go to reconcile, never new attempt |
| 8 | Problem still true | tracking fact still LATE/LOST (not DELIVERED); case window held | HUMAN_REVIEW (note "delivered after report") |
| 9 | Durable intent | in ONE transaction: insert `refund_attempt` (status REQUESTED, new `request_id`, unique `invoice_id`, amount, capture_id) + outbox `refund.requested` + CAS APPROVED->REFUNDING committed | abort, no PayPal call |

Then (not a numbered check): re-read flag immediately before the adapter call; the adapter independently re-checks freeze, ceiling, `request_id` presence, amount-vs-ledger, and ticket (defense in depth, threat-model section 10).

## 7. Refund execution (SPIKE-VERIFIED facts, V)
Facts used: unique refund per case is OUR constraint; PayPal allows several partials per capture and capture reads PARTIALLY_REFUNDED after a partial (V); replay with same `PayPal-Request-Id` returns the ORIGINAL refund even if the amount differs (V, so we enforce same-amount ourselves); reusing `invoice_id` -> 422 DUPLICATE_INVOICE_ID (V); over-refund -> 422 REFUND_AMOUNT_EXCEEDED (V); two concurrent identical requests -> one 201, one 409 (V); `GET /v2/payments/refunds/{id}` works (V). PENDING refund status: not tested (I).

Attempt state: `REQUESTED -> SENT -> COMPLETED | FAILED | UNKNOWN`; plus `NOT_SENT`. `UNKNOWN` can return to `SENT` (reconcile) and end COMPLETED/FAILED.

Sequence:
1. Check 9 commits attempt: `request_id = uuid4` (persisted BEFORE the call), `invoice_id = "PS-" + case_id` (unique per refund; one refund per case so unique per case), `amount_minor`, `capture_id`, `ticket` data.
2. Call adapter `refund_capture(request_id, invoice_id, capture_id, amount, authorization ticket)`; set attempt `SENT` with `sent_at` in a separate short transaction after the HTTP call returns or times out (the REQUESTED row already proves intent).
3. Interpret result:
   | adapter/PayPal result | attempt | case |
   |---|---|---|
   | 201 COMPLETED | COMPLETED (store `paypal_refund_id`, status) | T18 RESOLVED_REFUNDED, emit `refund.completed` |
   | 201 PENDING (I) | SENT (in progress) | stay REFUNDING, poll |
   | 409 | SENT (IN_PROGRESS) | stay REFUNDING; poll `GET refund` / reconcile; never blind retry; emit nothing |
   | timeout / 5xx / connection error | UNKNOWN | stay REFUNDING; `refund.unknown` |
   | 422 REFUND_AMOUNT_EXCEEDED | FAILED(reason) | T19 HUMAN_REVIEW; `refund.failed` |
   | 422 DUPLICATE_INVOICE_ID | FAILED -> reconcile first (may mean our earlier send succeeded) | if reconcile finds it, COMPLETED; else T19 |
   | adapter refuses frozen/ceiling/ticket | NOT_SENT | T20 back to APPROVED (frozen) or T19 (ceiling/ticket) |
   | 401 (token) | adapter handles refresh; if surfaced -> UNKNOWN | stay REFUNDING |
4. Never create a second `refund_attempt` for the same case; "retry" always means reconcile of the existing attempt.

Refund note to payer is a neutral template (no accusation). After COMPLETED: notify buyer in-app.

## 8. Reconciliation job
- Entry: `POST /refunds/reconcile` (svc:poller/operator) and an in-process asyncio loop every `PS_RESOLUTION_RECONCILE_INTERVAL_S` (external GitHub Actions/cron hitting `/internal/tick` is the backup, per deployment doc). Idempotent; safe to call concurrently (row lock below).
- Select: attempts in SENT/UNKNOWN older than `PS_RESOLUTION_REFUND_MIN_RECONCILE_AGE_S`, `FOR UPDATE SKIP LOCKED`, ordered oldest first.
- Per attempt:
  1. Known `paypal_refund_id`: `GET refund` -> COMPLETED -> finalize (T18); FAILED/CANCELLED -> FAILED (T19); PENDING/in progress -> leave, increment `reconcile_count`.
  2. Unknown refund id (response lost): ask the adapter to `reconcile_refund(request_id)` = idempotent replay of the identical stored request (same Request-Id, same invoice_id, same amount; PayPal returns the original, V; adapter ledger refuses a changed amount). 201/200 original -> finalize. 409 -> still in progress. This is a lookup by replay, not a new refund. Needs the adapter op (conflict C4). Cross-check capture remaining refundable (field name unverified, I).
  3. Mismatch (PayPal refund amount != attempt amount, unexpected refund on capture, repeated UNKNOWN > `PS_RESOLUTION_RECONCILE_MAX_ATTEMPTS`) -> set `needs_review`, case T19 HUMAN_REVIEW, emit `refund.unknown`, request auto-freeze (trigger listed in threat-model section 10).
- When frozen: reconcile still READS (GET) and finalizes completed refunds; it never SENDS a new request while frozen (replay is a send; skipped if frozen, flagged pending).
- Output: `{examined, finalized_completed, finalized_failed, still_unknown, needs_review}`.

## 9. Kill switch (REFUNDS_FROZEN)
- Source of truth: `resolution.control_flags` row (`refunds_frozen bool`, `reason`, `set_by`, `set_at`, `epoch`). Absent/unreadable/stale-read error = frozen.
- Checked: (a) before offer auto-execution, (b) check #1, (c) immediately before the adapter call, (d) in reconcile before any replay-send. Cache <= `PS_RESOLUTION_FLAG_CACHE_TTL_S` (few seconds, I); a toggle bumps `epoch` and invalidates the local cache.
- Stop wins: freeze beats approvals, in-flight APPROVED, retries and poller; APPROVED items remain queued and run after unfreeze (they re-run all 9 checks).
- Adapter mirror: to avoid an upward call (adapter -> resolution breaks P5), resolution pushes the flag to the adapter (`PUT /v1/controls/refunds-frozen`) on every toggle with retry until ACKED; response exposes `adapter_mirror: ACKED|PENDING`. Resolution's own gates already hold while PENDING (conflict C3).
- Unfreeze: operator role (not merchant), mandatory reason, audited, emits `case.*`-namespaced event `case.control_changed`? No: toggle is audited via outbox event type `refund.freeze_changed` (producer resolution; added to event list, conflict C5).
- Auto-trip hooks (thresholds unset, I): reconcile mismatch, chain-verify failure signal, PayPal 5xx burst, injection spike.

## 10. Protection window and no auto-deny
- `protected_until` comes from checkout order facts (demo window, not PayPal's). Eligibility is judged at `case.opened_at` (signal or report time on the demo clock), then `window_hold=true`: while the case is in PROBLEM_DETECTED, TRIAGED, OFFERED, HUMAN_REVIEW, APPROVED or REFUNDING, the original eligibility stands regardless of `now`. Review delay cannot expire coverage (threat-model section 8).
- Offers/links expiring never deny: they move to HUMAN_REVIEW (T12) and the buyer can be re-offered.
- Only a human (reviewer) or the buyer can reach DECLINED; reason mandatory and audited.

## 11. Neutral wording and banned words
- All buyer-visible strings come from `domain/wording.py` templates (keyed by event); no free-form text reaches a buyer except `triage-ai` drafts that pass the gate; gate failure -> static template.
- Gate (applied to every buyer-visible and merchant-visible string, in code and unit-tested): reject URLs (`http`, `www`, `://`, markdown links), currency amounts in drafts (amounts come only from template slots filled by server values), and banned words (case-insensitive, stem match): fraud, fraudulent, suspect, suspected, suspicious, scam, abuse, abusive, cheat, dishonest, lie, lying, accuse, accusation, violation, flagged, blacklist, "your fault", rejected, denied.
- Reference templates: "We are checking your order." / "Your order looks late. Here is an offer." / "A person is reviewing your case; your coverage stays active." / "Your refund was sent." No claim of "PayPal-backed" or similar.
- Reviewer brief is internal only and exempt from banned-word rewriting but never shown to the buyer.

## 12. Human-review queue and SLA (demo target)
- Queue = cases in HUMAN_REVIEW ordered by `human_review_entered_at`; item shows reason codes, brief (from triage-ai `/brief`, static fallback), age and an SLA timer against `PS_RESOLUTION_HUMAN_REVIEW_SLA_TARGET_S`.
- The SLA is a DEMO TARGET (I), unset by default, never described as measured or promised. Real-operation target in threat-model (first human action within 1 business day) is a design intention only.
- Reviewer decisions (`POST /cases/{id}/review-decision`): `PROPOSE_REFUND` (creates offer/proposal -> tier 1 or 2), `PROPOSE_RESHIP`, `DECLINE` (reason required), `CLOSE` (reason). Name is self-asserted; stamped `reviewer_name_selfasserted`. Reviewer cannot call refund and cannot approve own proposal (buyer must).
- Merchant override (`POST /cases/{id}/merchant-action` type OVERRIDE_OFFER): builds NEW proposal with new `proposal_hash`, marks old offer SUPERSEDED, revokes old tokens, always tier 2.

## 13. Concurrency
- Case row: `version` CAS on every transition; `SELECT ... FOR UPDATE` on the case row in `AcceptOffer`, `ConsentApproval`, `ExecuteRefund`, `ReviewDecision`, `MerchantAction`.
- Single execution winner: `APPROVED -> REFUNDING` CAS inside check 9 transaction; losers read the existing attempt and return `IN_PROGRESS`/existing result (HTTP 200 with state, not an error).
- DB constraints as backstops: `UNIQUE(refund_attempts.case_id)`, `UNIQUE(refund_attempts.invoice_id)`, `UNIQUE(refund_attempts.request_id)`, partial unique on `refund_attempts(order_id) WHERE status IN (REQUESTED,SENT,UNKNOWN,COMPLETED)`, `UNIQUE(approvals.tid)`, `UNIQUE(cases.order_id, cases.kind)`, `UNIQUE(inbox_dedupe.event_id)`, `UNIQUE(idempotency_keys.key, route)`.
- Approval redemption and offer acceptance are conditional single-row UPDATEs (rowcount 1 wins).
- Use `pg_advisory_xact_lock` or row locks only (Neon pooler safe, I); no session advisory locks.
- Events: at-least-once; consumer dedupes by `event_id`; handler is a no-op when case exists.
- Outbox relay uses `FOR UPDATE SKIP LOCKED` so two relays do not double-send.

## 14. Config / env names (names only, no values, no secrets here)
| name | kind | note |
|---|---|---|
| PS_RESOLUTION_SERVICE_ID | config | `resolution` |
| PS_RESOLUTION_DATABASE_URL | secret | schema role for `resolution` only |
| PS_RESOLUTION_INTERNAL_JWT_SIGNING_KEY, PS_RESOLUTION_INTERNAL_JWT_KID | secret | key for tokens this service issues |
| PS_RESOLUTION_INTERNAL_JWT_TRUSTED_ISSUERS | config | static issuer/kid map (no runtime JWKS fetch, auth-gateway) |
| PS_RESOLUTION_MANDATE_URL, PS_RESOLUTION_CHECKOUT_URL, PS_RESOLUTION_TRACKING_URL, PS_RESOLUTION_TRIAGE_AI_URL, PS_RESOLUTION_PAYPAL_ADAPTER_URL, PS_RESOLUTION_AUDIT_URL | config | base URL or `inproc:` transport |
| PS_RESOLUTION_APPROVAL_LINK_HMAC_KEY | secret | approval token HMAC |
| PS_RESOLUTION_APPROVAL_LINK_TTL_S | config | 24 h default (I) |
| PS_RESOLUTION_APPROVAL_BASE_URL | config | public frontend origin for links |
| PS_RESOLUTION_POLICY_VERSION | config | pinned on every decision |
| PS_RESOLUTION_POLICY_REFUND_CAP_MINOR | config | illustrative (brief ~USD 50) |
| PS_RESOLUTION_POLICY_EXCLUDED_CATEGORIES | config | CSV, illustrative |
| PS_RESOLUTION_POLICY_VELOCITY_MAX, PS_RESOLUTION_POLICY_VELOCITY_WINDOW_DAYS | config | brief: >2 per 30 days, illustrative |
| PS_RESOLUTION_TRIAGE_MIN_CONFIDENCE | config | 0.7 is our own heuristic (I), not a standard |
| PS_RESOLUTION_TRIAGE_TIMEOUT_S, PS_RESOLUTION_ADAPTER_TIMEOUT_S | config | unset; choose in S3 |
| PS_RESOLUTION_PREAUTH_AUTO_EXECUTE | config | tier 0 on/off |
| PS_RESOLUTION_REFUNDS_FROZEN_DEFAULT | config | must be `true`; absence = frozen |
| PS_RESOLUTION_FLAG_CACHE_TTL_S | config | few seconds (I) |
| PS_RESOLUTION_RECONCILE_INTERVAL_S, PS_RESOLUTION_REFUND_MIN_RECONCILE_AGE_S, PS_RESOLUTION_RECONCILE_MAX_ATTEMPTS | config | unset |
| PS_RESOLUTION_HUMAN_REVIEW_SLA_TARGET_S | config | demo target, unset by default |
| PS_RESOLUTION_CASE_REPORT_MAX_CHARS | config | untrusted text cap |
| PS_RESOLUTION_OUTBOX_RELAY_INTERVAL_S | config | |
| PS_RESOLUTION_TICK_SECRET | secret | for `/internal/tick` from external cron |
| PS_RESOLUTION_DEMO_MODE | config | shows SIMULATED CARRIER / sandbox labels |

## 15. Conflicts and decisions (service-map.md and adr.md win)
| id | conflict | resolution |
|---|---|---|
| C1 | auth-gateway route table (`/orders/{id}/problem`, `/review/queue`, `/review/{id}/decision`, `/approvals/{token}`) vs service-map (`/cases/report`, `/approvals/{token}/consent`) | Follow service-map as upstream paths; gateway maps its edge routes to these. Added `/review/queue`, `/cases/{id}/review-decision`, `GET /approvals/{token}` as additions |
| C2 | service-map: resolution consumes only late/lost/mandate.revoked, but states PROTECTED/MONITORING exist | Lazy materialization with back-filled transitions; no `order.captured` subscription |
| C3 | threat-model: adapter reads the freeze row directly; ADR-004 forbids cross-schema SQL; calling resolution from adapter breaks no-upward-sync rule | Flag owned by resolution; resolution pushes a mirror to the adapter, fail closed on both sides |
| C4 | Adapter surface lacks a reconcile-by-Request-Id op (GET refund needs refund id we may not have) | Request adapter owner to add `reconcile_refund(request_id)`; relies on V replay behaviour; Request-Id retention window unknown (I) |
| C5 | Event list lacks freeze toggle and `case.state_changed` | Add `refund.freeze_changed` and `case.state_changed` (within `case.*` namespace); contracts under `contracts/events/` |
| C6 | overview: revocation "pauses un-executed offers" vs "protection stays for captured orders" | **Confirmed (D1, user, 2026-10-10)**: terms snapshot per case; revocation blocks new offers' pre-authorization only for cases not yet opened; opened cases keep their snapshot and protection stands. |
| C7 | Role names: service-map says merchant, auth-gateway adds reviewer and operator | Use buyer, merchant, reviewer, operator; scope `money.execute` held by resolution token to adapter |
| C8 | Health endpoints: auth/overview `/healthz`,`/readyz`; deployment `/health`,`/health/deep` | Implement `/healthz`, `/readyz`; add `/health` and `/health/deep` aliases |
| C9 | threat-model says over-cap and excluded category -> HUMAN_REVIEW while brief says outside terms -> fresh buyer approval | Policy hits go to HUMAN_REVIEW; reviewer then creates a proposal that still needs buyer approval (tier 2). Terms-only misses (amount over terms, not covered kind) go straight to tier 2 |
| C10 | Service name for resolution in auth matrix is `orchestrator` | Same service for token scoping purposes |

## 16. Events (outbox)
Emitted (envelope per overview section 7): `case.opened`, `case.triaged`, `case.state_changed`, `case.resolved`, `offer.created`, `approval.granted`, `refund.requested`, `refund.completed`, `refund.failed`, `refund.unknown`, `refund.freeze_changed`. Consumed: `shipment.late_detected`, `shipment.lost_detected`, `mandate.revoked`. Payloads carry ids, state, reason codes, minor-unit amounts; no free text, no tokens, no secrets, no PII beyond ids.
