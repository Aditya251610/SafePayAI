# audit - sprint tasks

Labels: V/VC/I. Dates per sprint-plan.md root (Oct 10 - Nov 10 2026; cut line Oct 23; freeze Nov 6). Every feature task is paired with a test task and a deploy task (sprint-plan.md standing rule sec 0). Audit's own rows below are a service-level breakdown of sprint-plan.md's S1-11 (and the audit-consuming parts of S2-06, S3 producers, S4 hardening); IDs here use an `AU-` prefix to avoid colliding with the root plan's `S1-xx` IDs while mapping 1:1 to the relevant root rows.

## Week 1: Oct 10-16 (Sprint 1, Days 1-7) - maps to root S1-04, S1-11

| ID | Feature task | Test task | Deploy task |
|---|---|---|---|
| AU-W1-01 | Alembic migration: schema `audit`, roles `audit_owner`/`audit_app`, grants (INSERT+SELECT only), 3 triggers (UPDATE/DELETE/TRUNCATE reject; BEFORE INSERT linkage check), genesis row (spec.md sec 2.1, sec 8) | test-plan.md sec 1 "Append-only enforcement" (grants + trigger denial, both roles) | Run `mig_audit` over Neon DIRECT endpoint on Profile B `core` host as deploy pre-step; confirm via `readyz` genesis-present check |
| AU-W1-02 | Canonicalization + hashing module (`app/chain/canonical.py`, `hashing.py`), RFC 8785 JCS, domain-prefixed SHA-256 (spec.md sec 4); golden vectors committed under `tests/vectors/` | test-plan.md sec 2 "Chain-verify" golden-vector check (L1, byte-exact) | n/a (pure library, ships with the service deploy in AU-W1-04) |
| AU-W1-03 | `POST /internal/events` (single, idempotent on `event_id`), advisory-lock append algorithm (spec.md sec 3), actor/producer allowlist check (spec.md sec 5) | test-plan.md sec 5 "actor allowlist" + REQ-AU-004 idempotency case (duplicate push returns same seq) | Deploy inside `core` process (Profile B); smoke test: push `mandate.signed` fixture event, confirm 201 then 200-duplicate on replay |
| AU-W1-04 | `GET /verify`, `GET /head` minimal (chain recompute + head export, no signing yet) | test-plan.md sec 2 happy path + `GENESIS_MISSING`/`HASH_MISMATCH` reason codes on a fresh DB | Deploy; hosted smoke per root plan S1 exit: "`mandate.signed` push from mandate outbox relay" visible via `/verify` |
| AU-W1-05 | `/healthz` (no DB) and `/readyz` (DB + genesis check) (REQ-AU-050) | Health-check unit test: `/healthz` makes zero DB calls (mock DB, assert never called) | Wire into UptimeRobot 5-min pinger on `core`/`edge` only, per deployment.md sec 5 - confirm pinger hits `/healthz`, not `/readyz` |
| AU-W1-06 | Redaction schema allowlist per-type (first 3-4 event types needed for W1 demo: `MANDATE_SIGNED`, `CART_CHECKED`/`BLOCKED`, `ORDER_CREATED`) | test-plan.md sec 5 redaction corpus (secret-pattern strings rejected) for these types | n/a (ships with AU-W1-03 deploy) |

W1 exit (maps to root S1 exit, sprint-plan.md sec 2): audit role verified on Neon (data-architecture.md open item 2 closed); chain verifies after a real `mandate.signed` append on the hosted demo; CI green on the 6 rows above.

## Week 2: Oct 17-23 (Sprint 2, Days 8-14) - CUT LINE Oct 23 - maps to root S2-06

| ID | Feature task | Test task | Deploy task |
|---|---|---|---|
| AU-W2-01 | `POST /internal/events/batch` (one lock, one commit, per-item REJECTED/APPENDED/DUPLICATE results) | test-plan.md sec 3 "Concurrent-writer" batch variant (gapless seq across the batch) | Deploy; wire checkout's and paypal-adapter's outbox relays to use batch where available |
| AU-W2-02 | Outbox-subscriber correctness: confirm audit absorbs at-least-once delivery from mandate, checkout, shopping-agent, paypal-adapter outboxes (root S2-06) without creating duplicate rows | test-plan.md sec 5 event-type-coverage check for the full W1+W2 type set (`MANDATE_*`, `CART_*`, `ORDER_*`, `PAYPAL_CALL_RECORDED`) | Deploy `/internal/outbox/flush`-triggered delivery path; confirm audit-down backlog drains after a forced outage (chaos C16 analog) |
| AU-W2-03 | Remaining event-catalog schemas for W2 producers: `CART_PROPOSED` (AI block fields), `ORDER_CAPTURED`, `ORDER_CAPTURE_FAILED`, `PAYPAL_CALL_RECORDED` | test-plan.md sec 5 schema/redaction tests for each new type; float-forbidden and AI-block-field checks (REQ-AU-032) | Deploy; smoke test against the hosted cut-line demo path (sign -> cart -> order -> capture) |
| AU-W2-04 | `GET /entries` (AG Grid server-side row model, buyer row-scoping) minimal version - needed so the cut-line demo can show "audit entry for mandate.signed visible" (root S1 demo increment wording, carried into S2 polish) | test-plan.md sec 1 row-scoping variant: buyer A cannot see buyer B's rows (IDOR pattern, test-strategy.md T10 analog) | Deploy; index checklist from spec.md sec 9 applied (`mandate_id`, `order_id` partial indexes) |
| AU-W2-05 | Idempotency-under-concurrency hardening: confirm `UNIQUE(prev_hash)`/`UNIQUE(row_hash)` fork guard holds when checkout + mandate + paypal-adapter all push near-simultaneously during the cut-line rehearsal | test-plan.md sec 3 full concurrent-writer test (N=20) run against the POOLED endpoint on hosted Profile B | n/a (verification task, not a new deploy) |

CUT LINE Oct 23 (root plan, sec 3, item 2): "Mandate/cart/order events present in audit chain and `/verify` is OK" is a pass/fail gate for the WHOLE project, not just audit - these rows exist to guarantee that line is true on the 5-consecutive-run check.

## Week 3: Oct 24-30 (Sprint 3, Days 15-21) - maps to root S3 (tracking/resolution/triage producers go live)

| ID | Feature task | Test task | Deploy task |
|---|---|---|---|
| AU-W3-01 | Event-catalog schemas for the hero loop: `TRACKING_*`, `CASE_*`, `TRIAGE_COMPLETED`, `OFFER_*`, `APPROVAL_*`, `REFUND_*` (full spec.md sec 6 catalog) | test-plan.md sec 5 schema tests per new type; REQ-AU-031 checks `checks[9]` array-shape validation for `REFUND_REQUESTED` | Deploy; smoke test against the hosted hero-loop path (late -> triage -> offer -> refund) |
| AU-W3-02 | `GET /entries/by-ref` (ordered trail per mandate/order/case, used by receipt and case pages) | Playwright/L5 check that the receipt "show proof trail" link renders the correct ordered trail | Deploy; wire into web's case timeline and receipt screens |
| AU-W3-03 | `GET /verify/last` (cheap cached verify-state for the grid header) | Unit test: returns last `verify_runs` row without a fresh full-chain recompute | Deploy |
| AU-W3-04 | Scheduled verify (REQ-AU-044): GitHub Actions cron calling `/verify`, failure surfaced to operator (no auto-trip of kill-switch - audit has no write path to `REFUNDS_FROZEN`, per conflict C9/C3) | test-plan.md sec 2 negative reason-code matrix re-run against the scheduled job's output format | Deploy `verify-cron.yml`; confirm it runs only in review windows per deployment.md sec 3 (not 24/7, to protect Neon CU-hours) |
| AU-W3-05 | Full tamper-demo script (REQ-AU-051) against a Neon branch scratch copy, including Step C (sophisticated-attacker, anchor-only detection) | test-plan.md sec 4 full tamper-detection test, all three steps | n/a (script runs manually/nightly against scratch, never against `main` branch - guard asserted in the script itself) |
| AU-W3-06 | Head export `GET /head` finalized with the `paste` string format and optional Ed25519 signing (REQ-AU-043, P1) | Unit test: paste string format matches spec.md sec 10 exactly; signature verifies against the committed public key when `PS_AUDIT_HEAD_SIGNING_KEY` is set | Deploy; first real head export committed to `docs/anchors.txt` as the W3 rehearsal anchor |

W3 exit (root S3 exit): "the full story... runs on the hosted demo 5 consecutive times" requires audit's full event catalog (AU-W3-01) and verify (inherited from W1/W2) to be green on every run; this week's rows are the audit-side precondition for that exit gate, not an independent one.

## Week 4: Oct 31 - Nov 6 (Sprint 4, Days 22-28) - FEATURE FREEZE Nov 6 - maps to root S4

| ID | Feature task | Test task | Deploy task |
|---|---|---|---|
| AU-W4-01 | `GET /export` (NDJSON) finalized; `scripts/verify_chain_standalone.py` (stdlib-only third-party verifier) | test-plan.md DoD item: standalone verifier agrees with `GET /verify` on the same exported data | Deploy; run once against the hosted `main` export as a cross-check before freeze |
| AU-W4-02 | AG Grid integration for the reviewer case queue / audit log view (shared with root S4-01, time-boxed, FIRST item on the project cut list) | Playwright grid test: filter/sort/export, chain-status column reflects real `/verify/last` state (no mock rows) | Deploy only if root S4-01 is not already dropped per the cut list; if AG Grid is cut, audit's `GET /entries` still ships as a plain table in web |
| AU-W4-03 | Hardening pass: rate limits on `/verify` and `/export` (gateway-owned, confirmed here), full redaction corpus re-run across the ENTIRE event catalog, env-manifest CI test confirming `PAYPAL_*`/`LLM_API_KEY` absent from audit's env | test-plan.md sec 5 full redaction + actor-allowlist matrix (test-strategy.md T13/T14 pattern) | Deploy; re-run full gitleaks history scan including audit's own module tree |
| AU-W4-04 | Tamper-demo re-run on Neon (required for S4 exit per test-strategy.md sec 8: "audit tamper test re-run on Neon" before freeze) | test-plan.md sec 4, full re-run, fresh scratch branch | n/a (verification task) |
| AU-W4-05 | Reliability soak contribution: audit survives the 10-consecutive-full-run soak (root S4-05) with zero manual fixes, including one run after 24h idle (cold-start path through `/readyz`) | Soak log entry per run: verify result, append latency, cold-start time if asleep | Nightly warm-up workflow continues to include audit's `/healthz` |
| AU-W4-06 | Docs: `docs/anchors.txt` procedure finalized (export before recording, again before submission); README honest-limits section matches spec.md sec 11 exactly (no "immutable"/"tamper-proof" wording anywhere) | Honest-claims grep (test-strategy.md T25) over README/UI/video script for banned audit-related phrases | n/a (doc-only, no service deploy) |

FEATURE FREEZE Nov 6 (Day 28): after this, only sev-1/sev-2 fixes, copy fixes, config hotfixes to audit - no new endpoints, no schema changes (root plan sec 5, applies verbatim to this service).

## Freeze/submit: Nov 7-10 - audit-specific checklist items only (full checklist is root sec 6)
- Nov 9 code freeze: re-run test-plan.md sections 1-4 one final time on the tagged `v1.0-submission` commit; confirm `GET /audit/head` paste string committed to `docs/anchors.txt` matches the chain's actual current head.
- Nov 10 submit morning: `GET /audit/verify` must return `ok: true` as part of the pre-submission smoke (root sec 6 "confirm demo warm").

## What to cut first (audit-specific, ordered; consistent with root plan's project-wide cut list sec 7)
1. AG Grid for the audit/reviewer view (AU-W4-02) - already item 1 on the PROJECT cut list; audit falls back to a plain paginated table via the existing `GET /entries` (no new work needed, it already exists for the grid).
2. Ed25519 head signing (REQ-AU-043, P1) - drop to unsigned head export only; `docs/anchors.txt` still works, just without a cryptographic signature backstop against a DB-only attacker (honest limit gets slightly weaker, state so in docs).
3. Scheduled verify cron (REQ-AU-044, P1) - fall back to on-demand verify only (judge/reviewer clicks the button); loses automatic staleness detection between demo runs but changes nothing about the core "tamper-evident" claim.
4. `audit_reader` read-only role for the standalone verifier (P2, spec.md sec 8) - the reviewer/operator role already covers `GET /export`; this is pure convenience, never required.
5. Per-mandate/per-order/per-case partial indexes beyond the PK and unique constraints (spec.md sec 9) - acceptable at demo row counts (Seq Scan is fine per data-architecture.md sec 13); only add if EXPLAIN ANALYZE shows a real problem.
- NEVER cut (matches root "never-cut" list plus audit's own non-negotiables): append-only enforcement (grants+triggers), the hash chain itself, `GET /verify` with full reason-code detection, idempotency on `event_id`, actor-stamping allowlist checks, redaction of secrets/PII from payloads, the tamper-demo's scratch-only guard.

## Conflicts/notes carried from spec.md sec 14 (not re-litigated here, see spec.md for resolution)
- C1 (route naming), C4 (actor attestation via producer token, not live user token, for outbox-delayed events), C6 (row-level scoping stricter than auth-gateway's original wording), C7 (dotted-to-UPPER_SNAKE event mapping), C9 (audit cannot auto-trip the kill-switch) all already resolved in spec.md with service-map.md/adr.md as the tie-breaker per this project's locked monorepo/service-map-wins rule; no new conflicts found while writing this sprint breakdown.
- Monorepo check: all deploy tasks above assume `services/audit/` inside the single public repo per ADR-009; no row here implies a separate repository for audit.
