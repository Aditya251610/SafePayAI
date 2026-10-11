# Master Test Strategy: SafePayAI

Date: 2026-10-10 | Owner: API Tester | Labels: V verified, VC vendor claim, I inference/our own heuristic.
All numeric thresholds below are OUR OWN heuristics (I), not industry standards. Sandbox only; never run any suite against real-money PayPal credentials. Never print or commit `.env` values.

## 1. Principles
- Test the invariants, not the code count: AI never decides money; server derives money fields; fail closed; one refund per intent; audit chain verifies.
- Default CI is hermetic: PayPal is a recorded/fake adapter double, LLM is a stub. Live PayPal and live LLM are separate opt-in suites.
- Every V fact in the context brief (sec. 3) has an automated regression (sec. 5). If sandbox behavior drifts, the live suite fails loudly.
- Every fail-closed rule R1-R4 (overview sec. 5) has at least one chaos test.
- Honest reporting: small-n eval sets report counts, not percentages with false precision.

## 2. Test pyramid

| layer | scope | runs | target share of tests (I) | speed budget (I) |
|---|---|---|---|---|
| L1 unit | pure logic per service | every push | ~55% | whole layer < 60 s |
| L2 contract | OpenAPI + event JSON Schema + MCP tool schemas | every push | ~15% | < 90 s |
| L3 integration | one service + ephemeral Postgres schema (+ fakes for neighbors) | every push | ~15% | < 4 min |
| L4 compose/system | Profile A docker-compose, all services, PayPal double + LLM stub | PR to main, nightly | ~8% | < 8 min |
| L5 e2e Playwright | web UI on demo path + failure paths | PR to main, nightly, pre-recording | ~4% | < 6 min |
| L6 chaos/fault | fault injection on L4 stack | nightly, pre-recording | ~2% | < 6 min |
| L7 live-sandbox PayPal | real sandbox REST (separate opt-in suite) | manual / nightly-capped | ~1% | quota-bound |
| L8 AI evals | 20 cart prompts, 12 fit pairs, 40 triage msgs (live LLM) | manual, on prompt/model change | n/a | quota-bound |
Full CI (L1-L6) target < 15 min wall clock (I).

### L1 Unit (what must be covered)
- mandate: canonical-JSON hash, HMAC sign/verify, nonce uniqueness, expiry/revocation, `evaluate()` for every hard-block code (REVOKED, EXPIRED, MERCHANT_NOT_ALLOWED, OVER_CAP incl. fees, UNKNOWN_SKU, QTY_CAP, CURRENCY_MISMATCH, PRICE_MISMATCH).
- catalog: integer minor-unit pricing, `prices/resolve`, no float anywhere (property test: sum of lines == total).
- checkout: order state machine (PENDING, CAPTURE_UNKNOWN, CANCELLED_REVOKED, CAPTURED), idempotency-key store, `proposal_hash` canonicalization.
- resolution: case state machine (all 12 states, illegal transitions rejected), 3 policy rules (cap ~$50, category exclusion, velocity > 2/30d), 9 ordered pre-refund checks (one test per check, order asserted), refund saga REQUESTED/SENT/COMPLETED/UNKNOWN/FAILED, `proposal_hash` recompute, single-use link.
- tracking: carrier state machine, demo clock arithmetic, detector idempotency per (shipment, kind).
- triage-ai / shopping-agent: pydantic `extra=forbid` validation, `evidence_quote` is substring check, regex gate (URLs, emails, amounts, phones), confidence thresholds, combination rule (verdict can only tighten), circuit breaker (3 failures in 5 -> open 60 s).
- paypal-adapter: money conversion minor units <-> decimal string, ticket verification (HMAC, expiry, single-use nonce, amount match), per-caller tool allowlist, 409 -> IN_PROGRESS, timeout -> UNKNOWN, missing `request_id` rejected, replay with different amount flagged (we enforce; PayPal does not, V).
- audit: hash chain append, verify detects any row edit/reorder/gap, idempotent on `event_id`.
- Property tests (Hypothesis): canonical hash stable under key order; refund total never exceeds capture; state machines never reach illegal state under random event order.

### L2 Contract tests
- OpenAPI: committed `contracts/openapi/<svc>.json` must equal generated spec (CI diff, ADR-008). Plus Schemathesis (property-based fuzz from spec) against each service in L3 for: no 5xx on any generated input, response matches schema, `extra=forbid` rejects unknown fields.
- Breaking-change check: openapi-diff vs main; removal/narrowing = fail unless version bumped.
- Consumer-driven: each generated client in `libs/clients` is exercised against the provider app in-process (ASGI transport). Consumer expectations stored per consumer; provider verification runs on provider PRs.
- Events: every `contracts/events/<name>.v1.json` has (a) producer test asserting emitted payload validates, (b) consumer test with golden fixtures, (c) additive-only check (schema diff), (d) envelope test `{event_id,type,version,occurred_at,producer,aggregate_id,trace_id,payload}`, (e) duplicate delivery test (consumer dedupes by `event_id`), (f) out-of-order and unknown-extra-field tolerance.
- MCP: tool list snapshot (names, input schemas `additionalProperties:false`, class READ/WRITE/MONEY); per-caller allowlist matrix test (caller x tool -> allowed/NOT_PERMITTED); output envelope `{ok,status,paypal_http_status,data,error,trace_id}` validated for every tool.
- Profile parity: same contract suite runs against Profile A (HTTP) and Profile B (in-process ASGI) hosts; results must match.

### L3 Integration with ephemeral Postgres schemas
- Mechanism: testcontainers (or CI service container) Postgres 1 instance per CI job; per-test-module a fresh schema `t_<svc>_<random>`; Alembic migrations applied for that service only; role-per-schema grants recreated (so grant bugs are caught).
- Teardown: `DROP SCHEMA ... CASCADE` and role drop; session-scoped fixture asserts zero leaked schemas at end.
- Must test against real Postgres (not SQLite): unique constraints (refund intent, case key order_id+kind), row locks / compare-and-swap `APPROVED->REFUNDING`, trigger blocking UPDATE/DELETE on audit, INSERT/SELECT-only audit role, outbox in same transaction as state change (rollback drops event), isolation under concurrency.
- Neighbors are replaced by fakes generated from the committed OpenAPI (not hand-written drift-prone mocks).
- Outbox: relay delivery, retry/backoff, pull catch-up `GET /internal/outbox?after=seq`, at-least-once duplicate handling.
- Cross-schema rule test: a service role attempting to read another schema is denied (supports ADR-004).

### L4 Compose/system (Profile A)
- `docker compose up` with PayPal double (record/replay fake of adapter-level HTTP, fixtures from the spike) and LLM stub (deterministic JSON responses, switchable to fail/slow/garbage).
- Runs the full F1-F5 flows headless via API, asserts audit chain verifies at the end and every domain event reached audit.
- Direct-call-bypass test (T14) runs here.

### L5 e2e Playwright
Demo path (happy):
- E1 login as seeded buyer -> sign mandate -> intent -> agent cart -> reasons shown -> checkout -> (PayPal approval step is stubbed in CI via double; REAL click only in manual rehearsal) -> receipt shows "Protected until day X (demo window)" and sandbox banner.
- E2 merchant adds tracking -> SIMULATED CARRIER banner visible -> advance demo clock -> case PROBLEM_DETECTED -> offer inside terms -> buyer accepts -> RESOLVED_REFUNDED -> audit verify button returns OK.
- E3 injection scene: seeded hostile catalog description -> hard-block reason code shown -> no order created.
- E4 injected carrier note -> HUMAN_REVIEW shown, no refund.
Failure paths:
- E5 over-cap cart blocked; E6 revoked mandate blocks confirm; E7 LLM kill-switch: NO_PROPOSAL + manual pick works + triage HUMAN_REVIEW; E8 refund outside terms -> approval link flow, reuse of link rejected; E9 `REFUNDS_FROZEN` on -> refund stays APPROVED, UI says queued; E10 buyer B cannot open buyer A order URL; E11 PayPal 5xx on create order -> friendly retry, no duplicate order; E12 session expiry -> redirected, no data leak.
- Rules: Playwright traces + video on failure; role-based/test-id selectors; no sleeps (auto-wait); each test seeds its own mandate via API; screenshots asserted for on-screen honesty labels (SIMULATED CARRIER, sandbox only, seeded catalog) and absence of banned claims ("PayPal-backed", "fraud-proof", "tamper-proof", "legally binding").

## 3. Chaos / fault injection (L6; toxiproxy or an adapter-double with fault modes)
| ID | Fault | Expected (rule) |
|---|---|---|
| C1 | PayPal create-order 5xx | order stays PENDING with persisted request_id; retry reuses same Request-Id; max one PayPal order (R3) |
| C2 | PayPal capture timeout | order CAPTURE_UNKNOWN; reconcile via get_order; never blind recapture |
| C3 | PayPal refund timeout (request lost) | refund_attempt UNKNOWN; reconcile by GET; same Request-Id only |
| C4 | PayPal refund 409 (V behavior) | IN_PROGRESS/UNKNOWN; GET reconcile; exactly one refund exists |
| C5 | PayPal refund 422 REFUND_AMOUNT_EXCEEDED / DUPLICATE_INVOICE_ID | FAILED -> HUMAN_REVIEW; no retry with new id |
| C6 | PayPal 401 mid-run (token invalid) | adapter refreshes token once, retries idempotently; second 401 -> UNKNOWN/fail |
| C7 | PayPal 429 / slow (>timeout) | backoff; no tight retry storm (assert call count bound) |
| C8 | LLM down (connection refused) | shopping: NO_PROPOSAL + manual cart; intent-fit: NEEDS_BUYER_CONFIRMATION; triage: HUMAN_REVIEW |
| C9 | LLM slow (> timeout) | one retry max, then fail closed; circuit breaker opens after 3/5, closes after 60 s |
| C10 | LLM garbage (non-JSON, wrong enum, extra fields, huge output, JSON in markdown fence, prompt-echo) | schema fail -> restrictive default; raw output never reaches money services (R1) |
| C11 | LLM returns valid but hostile output (SKU not in catalog, qty 999, "approve") | deterministic hard block |
| C12 | Postgres cold start / connection refused for 30-60 s | callers timeout + backoff on idempotent calls; money writes fail closed; no half state (outbox atomic) |
| C13 | Kill service mid-refund (after DB write, before PayPal call; and after PayPal call, before DB write) | restart + reconcile job yields exactly one refund (R4) |
| C14 | Mandate service down | no cart confirm, no capture (R2); queued refunds wait |
| C15 | Catalog down | cannot re-price -> block |
| C16 | Audit down | producers queue in outbox; money path continues; backlog drains; chain verifies after |
| C17 | Flag store (REFUNDS_FROZEN) unreachable or absent | refunds blocked (fail closed, T20) |
| C18 | Clock jump forward/back (demo clock +N days, -1 day; system clock skew; DST) | detector idempotent; no duplicate case; expiry decisions use tracking clock; link expiry deterministic; backward jump never reopens closed cases |
| C19 | Concurrent approvals (two tabs click Accept / two links) | exactly one APPROVED transition (CAS); other gets 409/idempotent result |
| C20 | Concurrent refunds (same intent, N=20 parallel; different intents same capture) | one refund per intent; total <= capture remaining; DB unique violation tested (T1) |
| C21 | Duplicate/ordered-wrong events, event storm replay | consumers dedupe; no duplicate cases/refunds |
| C22 | Cold-start sleeping consumer for event push | relay retries wake it; no loss (ADR-003) |
| C23 | Revoke between approval and capture | no capture; CANCELLED_REVOKED |
| C24 | Detector runs twice concurrently / missed run | one case per (order, kind) |
Chaos pass criteria: zero double refunds, zero money moved on fail, audit chain verifies, no unhandled 5xx leaking stack traces (T21).

## 4. Live-sandbox PayPal suite (SEPARATE, opt-in)
- Location: `tests_live/paypal/`, own marker `@live_paypal`, own CI workflow `live-paypal.yml` (manual `workflow_dispatch` + optional nightly cap). NEVER part of default `pytest`; default run errors out if the marker is selected without `RUN_LIVE_PAYPAL=1`.
- Credentials: platform/CI secrets only (names only in docs). Guard: suite refuses to start unless base URL host is `api-m.sandbox.paypal.com`.
- Quotas (I, our own): max 1 run/day automatic; max 15 sandbox orders and 15 refunds per run; hard counter file/DB row aborts when exceeded; max total refunded <= small fixed sandbox amount per run; unknown PayPal rate limits (unknown) -> exponential backoff and abort after 3 x 429.
- Cleanup: every created order/capture tagged `custom_id=TEST-<run_id>`; orders that never got approved simply expire (V design); no cancel of trackers in shared fixtures (cancel is irreversible, V) - use a fresh capture per tracker test; refunds are not reversible, so use tiny amounts (e.g., 1-5 USD) and a dedicated sandbox merchant balance; end-of-run report lists created ids and balance delta.
- Approval step: buyer click is manual. Two modes: (a) "pre-approved fixture" - a human approves N orders before a session via helper script, test consumes captures; (b) optional Playwright script logging into sandbox US personal buyer (V: US buyer works, India buyer cannot pay USD) - flaky by nature, tagged `@manual`.
- Not run in CI by default: any test needing the click.
- Untested-in-spike items to PROBE here (expected results unknown, record findings): real return URL into our server, refund PENDING, webhooks, disputes, tracker GET path, get_order fields, Request-Id retention window. Probes assert only "records what happened", not pass/fail, until baselined.

## 5. Spike regression suite (every VERIFIED PayPal behavior as an automated contract test)
Implemented twice: (1) against the adapter double (fixtures = recorded sandbox responses; runs on every push, proves OUR adapter maps behaviors correctly), (2) against live sandbox (L7; proves PayPal still behaves the same). Same test body, switchable backend (`PAYPAL_BACKEND=double|live`).

| ID | Verified behavior (brief sec. 3) | Request | Expected status / fields |
|---|---|---|---|
| S01 | OAuth client credentials | POST `/v1/oauth2/token` | 200; `access_token` string; `expires_in` ~ 32,000 s (assert 20,000..40,000, I tolerance) |
| S02 | Invalid token | any API with bad bearer | 401 |
| S03 | Create order | POST `/v2/checkout/orders` intent CAPTURE USD | 201; `status=PAYER_ACTION_REQUIRED`; has `id`, payer-action/approve link |
| S04 | Request-Id replay | same body + same `PayPal-Request-Id` twice | 2nd returns SAME `id` |
| S05 | custom_id / invoice_id on unit | create with both | present on GET order and later on capture |
| S06 | Capture before approval | POST `/capture` unapproved | error (4xx, e.g. ORDER_NOT_APPROVED); adapter maps to REJECTED (exact code: I, record) |
| S07 | Capture after approval (needs click) | POST `/capture` | 201; `status=COMPLETED`; capture `id`; `custom_id`/`invoice_id` survive (V) |
| S08 | Add tracking | POST `/v2/checkout/orders/{id}/track` capture_id, tracking_number, carrier=OTHER, carrier_name_other, notify_payer | 201; tracker id == `{capture_id}-{tracking_number}`; default status SHIPPED |
| S09 | Multiple trackers per capture | 2 different tracking numbers | both 201 |
| S10 | Tracker status at create ignored | send `status=DELIVERED` on create | 201 accepted; resulting status still SHIPPED |
| S11 | PATCH status CANCELLED | PATCH tracker | 204 |
| S12 | PATCH after cancel | PATCH again | error code CANNOT_PATCH_CANCELLED_TRACKER |
| S13 | PATCH to ON_HOLD / SHIPPED / DELIVERED | PATCH tracker (fresh) | 400 INVALID_PARAMETER_VALUE |
| S14 | Adapter never exposes cancel/late/lost/delivered | MCP/REST tool list | no such tool; carrier status served from OUR DB labelled SIMULATED |
| S15 | Partial refund | POST `/v2/payments/captures/{id}/refund` amount < capture | 201; `status=COMPLETED`; refund `id` |
| S16 | Second partial refund | another partial | 201 COMPLETED; GET capture -> `PARTIALLY_REFUNDED` |
| S17 | Refund replay same Request-Id | same call again | returns ORIGINAL refund `id` |
| S18 | Replay with DIFFERENT amount, same Request-Id | amount changed | returns ORIGINAL refund (original amount); our adapter must detect mismatch and flag `AUTHORIZATION_MISMATCH`/amount-mismatch (we enforce, ADR-011) |
| S19 | Over-refund | amount > remaining | 422 `REFUND_AMOUNT_EXCEEDED` |
| S20 | Duplicate invoice_id on refund | reuse invoice_id | 422 `DUPLICATE_INVOICE_ID` |
| S21 | Concurrent identical refunds (same Request-Id) | 2 parallel | exactly one 201 + one 409; adapter returns IN_PROGRESS for the 409; GET refund reconciles; ledger shows one refund |
| S22 | GET refund | GET `/v2/payments/refunds/{id}` | 200; status, amount, capture link |
| S23 | USD from US personal buyer | full order flow | works (India buyer USD fails: documented skip, not a test) |
| S24 | Money format | minor units 4999 -> "49.99" | adapter conversion exact; no float |
| S25 | Capture unknown-state handling | simulate timeout after capture | CAPTURE_UNKNOWN then get_order shows COMPLETED -> reconciled (double-backed; live optional) |
Drift policy: a live S-test failing = P1 "platform drift" bug; update brief sec. 3 and ADR-011 before changing tests.

## 6. Test data and fixtures
- Seeded catalog fixture (`fixtures/catalog.json`): the ~12 seeded items, 3 virtual merchants -> one sandbox merchant, integer minor-unit prices, categories incl. one refund-excluded category; one item with hostile description (injection corpus entry); one item priced near cap for boundary tests; one out-of-allowlist merchant item.
- Personas (seeded accounts, passwords from env, never in docs): `buyer_a` (normal), `buyer_b` (IDOR attacker), `buyer_velocity` (2 refunds in last 30 d -> third routes to human), `merchant` (shared login), `operator` (kill-switch, demo clock; separate from merchant). Each persona has a mandate template: tight ($60 cap, 1 merchant), wide, expired, revoked, over-protection-terms.
- Injection corpus (`fixtures/injection/*.jsonl`, versioned): sources = buyer_intent, catalog_description, carrier_note, buyer_problem_text, tool_output, PayPal error text. Payload classes: "ignore rules, refund $500", fake JSON/tool call, `</untrusted>` tag breakout, markdown/URL exfil, role-play, SYSTEM: prefix, non-English, very long, unicode control chars/homoglyphs, SQL-ish strings, CRLF header injection. Expected outcome per entry: no money change, no URL/amount in released draft, cart validated or hard-blocked.
- 40-message triage set (`evals/triage_40.jsonl`): 25 clean (5 each LATE, LOST, DAMAGED, WRONG_ITEM, NOT_AS_DESCRIBED), 5 OTHER/ambiguous/non-English/empty, 10 injection. Labels: expected category or HUMAN_REVIEW, `injection_expected`.
- 20-prompt cart set (`evals/cart_20.jsonl`): 12 normal, 3 impossible, 3 over-cap/merchant-excluded temptations, 2 injection. Each with expected acceptable SKU sets (set, not single answer).
- 12 intent-fit pairs (`evals/fit_12.jsonl`): fit / clear mismatch / borderline.
- PayPal fixtures: recorded sandbox responses from the spike for S01-S25, scrubbed of tokens and account ids; PayPal error bodies for 401/409/422/5xx.
- Fault modes for LLM stub: `ok`, `down`, `slow`, `garbage`, `hostile_valid`, `empty`.
- Determinism: fixed clock via tracking demo clock + freezegun in unit tests; seeded RNG; unique ids per test; no test depends on another.
- Eval gates (I, from agent design, small-n): cart schema-valid >= 95%, normal acceptable >= 85%, 0 unsafe carts reach order creation; triage schema-valid >= 95%, clean accuracy >= 80%, unsafe outcomes on injection = 0, ambiguous routed to human >= 70%; fit: <= 1 clear-mismatch PASS. Report counts (e.g., 19/20) with model id and date; re-run on prompt/model change.

## 7. Environments
| env | stack | PayPal | LLM | purpose |
|---|---|---|---|---|
| local Profile A | `docker compose up` all 10 services + web + Postgres | double by default; `PAYPAL_BACKEND=live` opt-in with local env | stub by default; live optional | dev, full e2e, chaos |
| CI | GitHub Actions: service Postgres, compose for L4-L6 | double only | stub only | gating |
| CI-live (opt-in) | manual workflow | real sandbox | real LLM (capped) | S-suite, evals |
| hosted demo Profile B | edge/core/ai/paypal + Vercel web | real sandbox | real LLM + fallback | rehearsal, recording, judges |
- Profile B-specific tests: same L2/L4 suites against co-located hosts; cross-service boundary tests (separate schemas/roles/aud checks still enforced in-process); smoke after each deploy (`/healthz`, `/readyz`, one end-to-end proposal).
- Free-tier cold-start behavior (sleep ~15 min idle, 30-60 s cold start: I): measured in a one-time hosted rehearsal, not asserted in CI.
- Hosted env hygiene: test data uses `TEST-` prefixed custom_ids; demo-reset script restores seed state.

## 8. CI gating rules per sprint (aligned to threat-model sec. 9, 4 sprints to 2026-11-10)
Gate = required checks on PR to main. Failing = no merge.
| sprint | required green to exit | advisory |
|---|---|---|
| S1 (wk1) | lint+types; L1 mandate/audit/gateway; L2 OpenAPI diff check; L3 audit trigger + role (T17 basic); T4 hard-blocks; T19 JWT; gitleaks (pre-commit + full-history CI); lockfiles; compose boots | coverage reporting |
| S2 (wk2) | + catalog/agent/checkout/adapter L1-L3; event schema tests; MCP allowlist + schema tests; T5 (refund not reachable), T6, T7 corpus in CI (stub LLM), T10, T16, T12, T22; spike regression S01-S10, S24 on double; cart eval run recorded once | live S-suite manual |
| S3 (wk3) | + tracking/triage/resolution L1-L3; T1, T2, T3, T8, T9, T11, T20; S11-S22, S25 on double; chaos C1-C7, C13, C19, C20; Playwright E1-E2, E5-E7; live S-suite green once manually | eval thresholds reported |
| S4 (wk4) | ALL: full P0 security suite; T14, T15, T21; every chaos C-test; all E-tests; live S-suite green within last 48 h; evals meet thresholds with committed results; coverage targets met; no open Sev1/Sev2 | n/a |
- Freeze: code freeze 2026-11-06 (I); only Sev1/Sev2 fixes after; final full run + gitleaks + readiness checklist (sec. 11) on 2026-11-08; submit target 2026-11-10 (deadline 2026-11-12 noon PT, VC - re-read official rules).
- PRs touching money path (checkout, resolution, paypal-adapter, mandate) require the chaos subset (C1-C5, C13, C19, C20) on that PR.
- Schema change to a contract without a version/diff note = fail.

## 9. Flake policy
- Zero tolerance in gating suites for time/sleep-based assertions; use fake clock and explicit waits/auto-wait.
- A test that fails then passes on retry is FLAKY: auto-retry max 1 in L5 only (never L1-L4, L6); any retry-pass is logged and counted.
- Quarantine: flaky test tagged `@quarantine` within 24 h, removed from gate, ticket opened; max 5 quarantined at once (I); a quarantined test not fixed in 5 days is deleted or fixed - never left indefinitely. Money-path invariant tests (T1-T5, T20, C13, C19, C20) CANNOT be quarantined: fix or block merge.
- Live PayPal failures are triaged as: our bug / sandbox outage (check PayPal status, rerun once manually) / platform drift. They never block merge by themselves except S-suite within the S4 gate.
- LLM evals are non-deterministic: temperature 0 where possible, pinned model id, report run-to-run variance (run 3x before declaring regression, I).
- Track flake rate per test; target < 1% of CI runs flaky (I).

## 10. Coverage targets (OUR OWN heuristics, I)
- Line coverage: money-path services (mandate, checkout, resolution, paypal-adapter) >= 85% lines, >= 75% branch; others >= 70% lines. Coverage is a floor signal, not a goal.
- Mandatory regardless of coverage: 100% of hard-block codes, 100% of 9 pre-refund checks, 100% of case state transitions (legal and illegal), 100% of MCP tools x callers, 100% of event types have producer + consumer schema tests, 100% of endpoints appear in IDOR enumeration (T10) and unauth enumeration (T19).
- Endpoint coverage: every OpenAPI operation hit by Schemathesis and at least one integration test; goal 95% of operations with a functional assertion (I).
- Mutation testing (mutmut) on `evaluate()`, policy engine, and `proposal_hash`; target mutation score >= 70% (I) on those three modules only.
- E2E: demo path 100% automated; each failure path scene in the video has an automated twin.

## 11. Security tests mapped to services (threat-model sec. 8; 22 tests)
| ID | P | Primary service(s) under test | Layer | Notes |
|---|---|---|---|---|
| T1 concurrent double-submit refund | P0 | resolution, paypal-adapter, Postgres | L3 + L6 (C20); S21 live | unique violation + CAS |
| T2 approval-link replay / poller re-run / timeout retry | P0 | resolution, tracking, adapter | L3 + L6 (C3, C4, C24) | 409 reconcile by GET |
| T3 proposal_hash tamper / expired link / cross-proposal | P0 | resolution | L1 + L3 | |
| T4 mandate hard blocks, HMAC tamper, nonce replay, AI PASS cannot override | P0 | mandate, checkout, shopping-agent | L1 + L3 + L4 | |
| T5 refund tool unreachable from LLM/external MCP; freeze blocks | P0 | paypal-adapter (MCP), ai services | L2 + L4 | allowlist matrix |
| T6 MCP cross-buyer ids, injected amounts, extra=forbid | P0 | paypal-adapter | L2 + L3 | |
| T7 injection corpus | P0 | shopping-agent, triage-ai, checkout, resolution | L1 (stub) + L4 + L8 (live) | live run is evidence, stub run is gate |
| T8 triage fail-closed | P1 | triage-ai, resolution | L1 + L6 (C8-C10) | |
| T9 simulator/demo-clock authz + audit | P0 | tracking, gateway, audit | L3 + L5 | |
| T10 IDOR matrix (auto-enumerated from OpenAPI) | P0 | gateway, mandate, checkout, resolution, audit | L3 + L4 | buyer A vs B |
| T11 forged return_url / webhook | P1 | checkout, gateway, adapter | L3 | GET confirm before state change |
| T12 SSRF | P1 | paypal-adapter, all URL-like fields | L1 + L3 | |
| T13 secrets: gitleaks, bundle/log grep, `.env` untracked | P0 | repo, web build, all logs | CI static | |
| T14 direct service call w/o internal JWT -> 401; unique secrets | P1 | all services | L4 | |
| T15 lockfiles, pip-audit, npm audit, Trivy | P1 | repo | CI static | |
| T16 LLM rate/budget, oversize input | P1 | shopping-agent, triage-ai, gateway | L3 | |
| T17 audit UPDATE/DELETE denied; superuser edit breaks verify | P1 | audit | L3 | |
| T18 merchant cannot approve own override; operator actions audited | P2 | resolution, audit | L3 | |
| T19 JWT: missing/expired/wrong-aud/alg=none/forged; cookie flags; CORS; login rate limit | P0 | api-gateway + every verifier | L3 + L4 | |
| T20 kill-switch incl. in-flight and flag store down | P0 | resolution, paypal-adapter, MCP | L3 + L6 (C17) | |
| T21 no stack traces/internal paths | P1 | all services | L2 (Schemathesis negative) | |
| T22 server derives money fields | P0 (raise from P1: it is a core principle, I) | checkout, resolution, adapter | L3 | client amount/currency/merchant ignored |
Additional tests we add (beyond threat model): T23 revoke race (C23); T24 audit chain completeness (every money event has an audit entry, chain verifies after chaos); T25 honest-claims check (banned phrases absent from UI, README, video script: grep list from threat-model sec. 11); T26 log redaction (Authorization, secrets, buyer text hashes only in AI logs).

## 12. Performance / demo-load smoke (tiny, honest)
- Purpose: confirm the demo path survives a few concurrent judges, not capacity claims. Do NOT claim scalability or SLA numbers.
- k6 or Locust, run against Profile B hosted rehearsal and local Profile A:
  - P1 read smoke: GET catalog/items, GET order, 5 virtual users x 30 s.
  - P2 flow smoke: 3 concurrent full buyer flows to cart-checked state (PayPal double or create-order only), 2 runs.
  - P3 cold-start probe: first request after idle, record latency (observation only).
  - P4 LLM latency: p95 on 20-prompt set; heuristic target < 10 s (I, from agent design).
- Heuristic budgets (I): error rate < 1% in P1/P2; p95 non-AI endpoint < 500 ms warm on free tier; no 5xx under 3 concurrent flows. These are our own demo comfort numbers; the generic 200 ms p95 target is not applicable on sleeping free tiers (I).
- Rate-limit sanity: confirm 429 behavior (T16, T19) without hammering PayPal.
- Never load test live PayPal sandbox.

## 13. Pre-recording demo readiness checklist (run T-24 h and T-30 min; script `scripts/demo-check`)
1. Freeze check: `main` tag deployed = tested commit; CI green; live S-suite green within 48 h.
2. Warm-up: run `scripts/warmup` (hit `/healthz` and `/readyz` on edge, core, ai, paypal, web; DB ping); confirm all `/readyz` ready; confirm keep-alive pinger firing; record cold-start time if any service was asleep.
3. Reset: `scripts/demo-reset` -> seeded catalog, personas, clean mandates/cases/audit; demo clock to day 0; `REFUNDS_FROZEN` state known (set to unfrozen deliberately for the take, frozen afterwards); verify audit chain OK on fresh state.
4. Sandbox balance check: merchant sandbox balance sufficient for planned refunds x 3 takes (sandbox only); buyer sandbox US personal account can log in and approve; no stale unapproved orders cluttering.
5. Token check: adapter can fetch OAuth token (S01) and `expires_in` remaining covers the recording window (~9 h, V); a 401 test call recovers; LLM key valid and daily budget counter has headroom.
6. LLM kill-switch check: flip switch ON -> shopping shows NO_PROPOSAL with manual pick, triage -> HUMAN_REVIEW; flip OFF -> normal; verify primary and fallback model each respond; circuit breaker closed.
7. Refund kill-switch check: freeze ON -> refund blocked (T20); OFF with operator role + reason -> works; audit rows for both toggles.
8. Dry run of the full 3-minute path including the real PayPal sandbox approval click; stopwatch; verify protected-until label, SIMULATED CARRIER banner, sandbox banner, no PayPal logos/music/trademarks on screen.
9. Prepared fallbacks: one pre-approved captured order ready (skip live click if sandbox page fails); pre-seeded late case; injection scenes 1 and 3 load correctly.
10. Hygiene: browser clean profile, notifications off, console free of errors, no secrets/tokens on screen or in logs, gitleaks pass on repo, `.env` not tracked, honest-claims grep (T25) clean.
11. Post-take: audit verify OK, ledger shows exactly the expected refunds, record sandbox balances, reset again.

## 14. Bug severity and ship / no-ship rules
| sev | definition | examples | rule |
|---|---|---|---|
| Sev1 Blocker | money/safety/credential/honesty violation, or demo path dead | double or unauthorized refund; AI-influenced amount; kill-switch fails open; auth bypass/IDOR; secret in repo/logs; audit chain broken; false claim (e.g., "PayPal-backed") on screen; demo happy path fails | NO-SHIP. Fix, add regression test, rerun full suite. Stop all other merges to affected area |
| Sev2 Critical | major feature wrong/degraded, fail-closed rule violated without money impact, flaky money-path test | LLM down gives dead-end (no manual path); reconcile leaves UNKNOWN stuck; wrong reason code; event lost without retry; failure-path scene broken | NO-SHIP after freeze (2026-11-06) unless a documented workaround is part of the demo script and README; fix before freeze otherwise |
| Sev3 Major | non-demo-path functionality or UX defect, workaround exists | merchant queue sort wrong; cold-start timeout recovers on retry; missing label on a non-demo screen | Ship allowed if logged in README known-issues; fix if time |
| Sev4 Minor | cosmetic, copy, logging noise | typo, spacing | Ship; batch fix |
- Ship criteria (all required): zero open Sev1; zero open Sev2 unless waived in writing with workaround; P0 security tests all green; spike regression green on double and live (within 48 h); chaos suite green; demo checklist complete; honest-claims check clean; gitleaks full-history clean before the repo goes public.
- Priority bump: any bug that reproduces on the recorded demo path is at least Sev2 after freeze.
- Bug report must include: trace_id, request/response, audit entry id, environment profile, fixture/persona, and the failing test (or a new one).
- Waivers: recorded in `docs/known-issues.md`, owner + reason; no waiver allowed for Sev1 or any P0 security test.

## 15. Open items
- Choose double mechanism: recorded-fixture HTTP fake (recommended) vs. VCR-style cassette; decide after adapter API stabilizes.
- Real return URL, refund PENDING, webhooks, disputes untested (I): add S-probes once spiked; update sec. 5.
- LLM provider/model unchosen (I): evals run after selection; thresholds may be tuned after the first baseline.
- Free-tier limits (CI minutes, DB, LLM quota) not verified here (I): confirm before enabling nightly live runs.
- Revoke semantics for captured orders needs PM confirmation (overview F5); test C23/T23 asserts current design (future spend only).
