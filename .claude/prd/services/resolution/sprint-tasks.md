# resolution: sprint tasks

Labels V/VC/I. Aligned to `sprint-plan.md` (S2-11 stretch skeleton, S3-02..S3-08, S3-12, S4 hardening). Dates: Week 1 Oct 10-16, Week 2 Oct 17-23 (DAY-14 CUT LINE Thu Oct 23), Week 3 Oct 24-30, Week 4 Oct 31-Nov 6 (FEATURE FREEZE Fri Nov 6), Nov 7-10 bug fixes only, code freeze Nov 9, submit Nov 10. Every feature task (F) has a paired test task (T, IDs from test-plan.md) and deploy task (D). Build volume is not the constraint; human review of money-path code is (review depth: deep on resolution).

Rule: resolution is OFF the cut-line path. The cut line (Oct 23) needs mandate -> order -> receipt; resolution work in weeks 1-2 is contracts and a pure-code skeleton only, behind a feature flag, and stops first if the cut line is at risk.

## Week 1 (Oct 10-16): contracts and pure core (no money actions)
| ID | F: Feature | T: Test | D: Deploy |
|---|---|---|---|
| RS-S1-01 | Service scaffold: FastAPI app, `domain/ app/ ports/ adapters/` layout, `extra=forbid` models, error envelope, `/healthz` `/readyz`, env manifest with `PS_RESOLUTION_*` names | T: import-lint (`domain/` imports nothing impure), forbidden-env-name test, deny-by-default token tests | D: mounted in `core` behind `PS_RESOLUTION_ENABLED=false` flag (I); `/healthz` smoke |
| RS-S1-02 | Contracts first: OpenAPI stub for api.md endpoints, 11 emitted + 3 consumed event JSON Schemas, envelope | T: contract lint, generated clients compile, CI spec-diff job | D: CI path-filtered workflow green |
| RS-S1-03 | Alembic 0001: schema `resolution`, role `resolution_app`, all tables, all unique/partial-unique constraints, `control_flags` seeded `refunds_frozen=true` | T: RS-T26, RS-T40, cross-schema denial test | D: migrate on Neon dev; verify grants limited to schema |
| RS-S1-04 | `domain/states.py`: 12-state transition table (T1-T27) as data + `apply_transition()` | T: RS-T01, RS-T02, RS-T03, RS-T04 | D: none (library) |
| RS-S1-05 | `domain/proposal.py`: JCS canonical `proposal_hash` | T: hash stable under key order; each field changes hash (T3 basis) | D: none |
| RS-S1-06 | `FlagPort` + `control_flags` read with fail-closed semantics | T: RS-T62 (absent/unreadable = frozen), cache/epoch RS-T68 | D: seed row present on Neon |
| RS-S1-07 | Align conflicts C1-C10 (spec s15) with gateway, adapter (`reconcile_refund`, freeze mirror), tracking, triage owners | T: contract tests updated | D: none |
Exit gate: skeleton deployed disabled on Profile B, contracts committed, transition table property tests green.

## Week 2 (Oct 17-23): pure policy and checks (stretch S2-11); contracts frozen Day 8
Priority: only if the cut-line path (mandate -> order -> receipt) is on track; otherwise stop (sprint-plan section 3).
| ID | F: Feature | T: Test | D: Deploy |
|---|---|---|---|
| RS-S2-01 | Case open on event + lazy materialization, unique `(order_id, kind)`, `case_transitions`, outbox row in same txn | T: RS-T05, RS-T06, RS-T07 | D: behind flag; events from a tracking stub reach audit |
| RS-S2-02 | `domain/policy.py` `decide()` D0-D10, 3 illustrative policies | T: RS-T08, RS-T09, RS-T10, RS-T11 | D: none; config names set in `core` env |
| RS-S2-03 | `domain/checks.py`: 9 check functions + `run_checks()` ordering and fail-closed on exception | T: RS-T70..T79 as unit tests with fakes | D: none |
| RS-S2-04 | `domain/wording.py` templates + banned-word/URL/amount gate | T: gate tests; honest-claims lint | D: none |
| RS-S2-05 | Ports + HTTP/in-process adapters for mandate, checkout, tracking (facts read-only) with fakes from OpenAPI | T: consumer contract tests (both transports) | D: smoke against deployed `core` |
| RS-S2-06 | Prepare CI side-by-side jobs scaffold (profile-a / profile-b) | T: job runs RS-T01..T11 on both | D: required checks on main (non-blocking until S3) |
CUT LINE (Oct 23): resolution is not a pass criterion. Exit: pure core green, flag off in hosted env.

## Week 3 (Oct 24-30): the hero loop (critical path S3-01..S3-06 protected)
| ID | F: Feature (sprint-plan ref) | T: Test | D: Deploy |
|---|---|---|---|
| RS-S3-01 | Consume `shipment.late_detected`/`lost_detected` (S3-02), inbox dedupe, in-app notifications | T: RS-T07, RS-T55; consumer golden fixtures; C21, C24 | D: flag on; events flow tracking -> resolution -> audit |
| RS-S3-02 | Triage integration: `/classify` fail-closed, `TRIAGE_FAIL_CLOSED` (S3-03 dependency) | T: RS-T50..T54, T7, T8, C8-C10 | D: smoke against `ai` process; stub fallback |
| RS-S3-03 | Policy + offers inside terms, `POST /offers/{id}/accept`, tier 1 (S3-04, S3-05) | T: RS-T20, RS-T10; offer immutable; accept twice -> one result | D: deploy; policy shown read-only in UI |
| RS-S3-04 | Refund saga: check 9 txn, persisted `request_id` before call, result interpretation, `POST /refunds/reconcile`, in-process loop + `/internal/tick` (S3-06) | T: RS-T30..T39, RS-T23, RS-T24, S15-S22 on double, T1, C13, C3-C5 | D: deploy; GitHub Actions tick scheduled; sandbox refund visible with ID in UI |
| RS-S3-05 | Kill switch: `GET/PUT /controls/refunds-frozen`, adapter mirror push, operator-only, audited | T: RS-T60..T68, T20, C17, E9 | D: freeze drill on hosted `core`; runbook entry |
| RS-S3-06 | Out-of-terms approval link + consent (S3-07) | T: RS-T21, RS-T22, T2, T3, T12, E8; IDOR link test | D: deploy; link page wording states exactly what is approved |
| RS-S3-07 | Buyer problem report `POST /cases/report` (S3-08) | T: RS-T50, RS-T57, injection corpus, long input | D: deploy |
| RS-S3-08 | Review queue + review-decision + decline/appeal; SLA timer as demo target (REQ-RS-017) | T: RS-T02 transitions T13-T15, T24; reviewer cannot execute refund | D: deploy; queue visible in UI |
| RS-S3-09 | Merchant override (S3-12, cut-list candidate; only if S3 on track by Day 19, Oct 28) | T: RS-T25, T18; override never mutates old offer or refunds directly | D: deploy only if gate met |
| RS-S3-10 | Seed pre-made late order in MONITORING, reset keeps refunds frozen state rule (S3-10) | T: seed idempotent; reset does not unfreeze | D: nightly reset |
| RS-S3-11 | Both profile CI jobs blocking; chaos subset on resolution PRs | T: profile parity green | D: required checks on main |
Security gates S3 (merge-blocking): concurrency refund tests (RS-T20..T24), T1, T2, T3, T20, C13, C19, C20.
Exit: full story runs 5 consecutive hosted times; HUMAN_REVIEW failure path demonstrated; concurrency tests green in CI; first live S-suite pass recorded.
If behind at Day 19 (Oct 28): cut list immediately; protect RS-S3-01..RS-S3-05.

## Week 4 (Oct 31-Nov 6): hardening; FEATURE FREEZE Nov 6
| ID | F: Feature/hardening | T: Test | D: Deploy |
|---|---|---|---|
| RS-S4-01 | Read endpoints for grids (`GET /cases?status=`, review queue fields, sort/filter) for AG Grid (S4-01, cut first) | T: contract + IDOR enumeration | D: only if AG Grid proceeds |
| RS-S4-02 | Rate limits, payload caps, error pages, no stack traces; reconcile min-age and max-attempt values chosen and documented | T: T16 (oversize), T21 (Schemathesis negative), 429 path | D: config set in `core` |
| RS-S4-03 | Full P0 suite on both profiles; fix flakes; mutation run on policy/proposal/checks | T: all RS-T, T1-T22 resolution rows, every C-test | D: tag release candidate |
| RS-S4-04 | Chaos run: kill `core` mid-saga cold, adapter down, flag unreadable, audit down | T: RS-T30..T41, C13, C16, C17, C22 recorded | D: results logged |
| RS-S4-05 | Live-sandbox S-suite within 48 h of gate; observe PENDING if possible and update docs (I -> V or still I) | T: S15-S22, S25 live | D: none |
| RS-S4-06 | Soak: 10 consecutive hosted runs incl. one after 24 h idle; token refresh after > 9 h | T: soak script, zero duplicate refunds, zero unapproved out-of-terms | D: nightly warm-up workflow |
| RS-S4-07 | Honest-claims and neutral-wording lint on all buyer/merchant strings; copy freeze Nov 5 | T: banned-word gate + E-tier label checks | D: final copy deployed by Nov 5 |
| RS-S4-08 | Rollback drill: deploy previous SHA with refunds frozen, reconcile, unfreeze | T: drill recorded | D: SHA noted in sprint log |
FEATURE FREEZE (Nov 6 end of day): no new endpoints, no schema changes. Nov 7-10: sev-1/sev-2, copy, config hotfixes only; Nov 9 code freeze and tag `v1.0-submission`; final gitleaks full history.

## What to cut first (resolution items; order follows sprint-plan section 7 and spec fallbacks)
1. AG Grid read endpoints (RS-S4-01): plain tables.
2. Profile A hosted rehearsal: compose only (profile-a CI job stays).
3. Merchant override (RS-S3-09): merchant view only; stated as future.
4. Reviewer brief (`/brief`): reviewer reads case timeline.
5. AI drafts (`/draft`): static templates (also safer).
6. Out-of-terms approval link (RS-S3-06): anything outside terms goes to HUMAN_REVIEW; story still complete.
7. Buyer free-text report (RS-S3-07): detector-originated LATE/LOST only.
8. Policy reduced from 3 rules to refund cap only (RS-S2-02 scope), labelled illustrative.
9. Tier 0 auto-execute (`PS_RESOLUTION_PREAUTH_AUTO_EXECUTE`): off by default, tier 1 click remains (I, own addition).
10. Escalation LATE -> LOST (P2, T27), per-mandate freeze, SLA timer display.

Never cut: 12-state table with `case_transitions`; 9 ordered checks; persisted `request_id` before the call; reconcile; unique refund per case; REFUNDS_FROZEN fail-closed; no auto-deny; HUMAN_REVIEW fail-closed; concurrency and crash tests; audit events; honesty labels; CI + gitleaks.

## Review load (human)
- Deep review: RS-S1-04, RS-S2-02, RS-S2-03, RS-S3-03, RS-S3-04, RS-S3-05, RS-S3-06 (state table, policy, checks, saga, freeze, approval). Skim with test evidence: wording, read endpoints, seed.
- Open PR limit per track: 3 (sprint-plan). Contracts additive-only after Day 8 (ADR-008).
