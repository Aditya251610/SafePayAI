# mandate: sprint tasks

Labels V/VC/I. Aligned to `sprint-plan.md` (S1-07 mandate sign/revoke/evaluate, S1-11 audit push, S2-01 capture, S2-03 revoke e2e, S2-06 outbox, S3-04 policy vs terms, S4 hardening). Dates: today 2026-10-10 = Day 1. **Cut line: Thu Oct 23 (Day 14). Feature freeze: Fri Nov 6 (Day 28).** Nov 7-10 = bug fixes only (sev-1/2), code freeze Nov 9, submit Nov 10. Task owner type = AI coding agent + human review (deep review on this service: it is on the money path). Effort sizes are not estimated (build volume is not the constraint; review, concurrency testing and hosted verification are). Each feature task has a paired T (test) and D (deploy) task, using the deploy ritual from sprint-plan (CI green -> auto-deploy `core` -> health gate -> smoke -> `scripts/warmup`). Test IDs: `test-plan.md`.

| Week | Dates | Exit |
|---|---|---|
| W1 | Oct 10-16 | Signed mandate + hard-block evaluate + revoke live on hosted `core`; contracts committed |
| W2 | Oct 17-23 | Ledger (reserve/authorize/commit/release) + grant + events + race tests; cut-line path green |
| W3 | Oct 24-30 | Resolution integration (terms/grants), rotation drill, chaos subset, Profile A parity |
| W4 | Oct 31-Nov 6 | Hardening, docs, soak, verify demo, freeze Nov 6 |

## Week 1 (Oct 10-16): contracts, signing, evaluate, revoke
| ID | Feature task | Test (T) | Deploy (D) |
|---|---|---|---|
| MD-S1-01 | CONTRACTS FIRST: `contracts/openapi/mandate.json` (all endpoints in api.md incl. additive ones), event schemas (`mandate.signed/revoked/expired` + proposed three), error codes, hard-block code enum. Share with checkout, gateway, audit, resolution owners; settle conflicts C1-C13 (spec sec 12) in one 30-min review | T: contract lint, generated clients compile, mock server boots; CI spec-vs-code diff check | D: mock mandate server in `docker compose` so checkout/gateway are not blocked (S1-02) |
| MD-S1-02 | Skeleton: `services/mandate` FastAPI app, `libs/common` token verify (`aud=mandate`, deny by default), error model, JSON logging with redaction, config loader that fails closed without keys, `/healthz` `/readyz` | T: MD-T91, T96, T10 (boot without key), T93 | D: mounted in `hosts/core.py`; first hello deploy on Profile B (S1-04); env manifest committed |
| MD-S1-03 | Alembic 001: schema `mandate`, tables (spec sec 2), CHECKs, immutability triggers, role `svc_mandate` grants (INSERT/SELECT vs UPDATE split) | T: MD-T08, T35, T73; grants/trigger tests on real Postgres; cross-schema SELECT denied | D: migrate on Neon with real roles; confirm INSERT/SELECT-only role and triggers work on Neon (ADR-004 open item); record result |
| MD-S1-04 | `canon.v1` serializer, `mandate_hash`, HMAC sign/verify with domain separation, key loader (current + previous), integrity check (spec sec 3) | T: MD-T01..T07, golden vectors committed | D: `MANDATE_HMAC_KEY` + ids set only in Render env; hosted `/readyz` shows keys ok; no key in logs (T26 canary) |
| MD-S1-05 | `render.v1` + `POST /mandates/preview` + nonce issue/consume (`nonces`, `nonce_uses`) + `POST /mandates` with `Idempotency-Key` + outbox row `mandate.signed` | T: MD-T20..T24, T30..T33, T37, T38, T40..T47 | D: hosted sign works from web sign screen (S1-10); plain text shown equals `screen_text` |
| MD-S1-06 | `evaluate` with the closed hard-block list + advisory flags (separate type) (spec sec 6) | T: MD-T50..T59 (one failing fixture per code, E5 over-cap in Playwright with checkout) | D: checkout calls hosted mandate in-process; smoke "over-cap cart blocked with reasons" |
| MD-S1-07 | State derivation (revoked > expired > exhausted > active), `GET /mandates/{id}`, `/terms`, `/summary`, role views (B/M/O/S), ownership 404 | T: MD-T60..T62, T80, T90, T98; IDOR enumeration from OpenAPI | D: hosted read views; merchant minimal view checked |
| MD-S1-08 | `POST /mandates/{id}/revoke` (row lock, revocation insert, event) and lazy `mandate.expired` | T: MD-T61, T62, T6A, T81 | D: revoke button wiring on hosted UI deferred to S2-03; smoke revoke on throwaway mandate |
| MD-S1-09 | Outbox table + relay to audit (`POST /append`) for the 3 base events (S1-11 pairing) | T: MD-T9A, T9B; audit down -> events retained (C16 early) | D: `mandate.signed` visible in hosted audit chain, `/verify` OK |
| MD-S1-10 | Spike: Neon pooled endpoint with `SELECT ... FOR UPDATE` row locks and transaction-scoped timeouts; PayPal approval time vs reservation TTL (I) | T: MD-T7B first run (small); dated spike note | D: decision recorded (pooled vs direct URL for mandate pool); `PS_MANDATE_RESERVATION_TTL_SECONDS` proposal |
| MD-S1-11 | Human review: money-path code read (canon, HMAC, nonce, evaluate) + Gate review of D1 wording with user (ask for the D1 decision now) | T: review checklist logged | D: n/a |
Exit: sign -> over-cap block -> revoke works on the hosted URL 3 consecutive times; P0 cases of S1 gate green; OpenAPI committed; Neon roles verified; open PRs <= 3.

## Week 2 (Oct 17-23): ledger, grants, race, cut line
| ID | Feature task | Test (T) | Deploy (D) |
|---|---|---|---|
| MD-S2-01 | `mandate_spend` + `spend_reservations`: reserve (full evaluate under lock), release, GET reservation, lazy TTL release (spec sec 7) | T: MD-T70, T71, T72 (property), T73, T74, T76, T78, T79, T7A | D: checkout `confirm` calls reserve on hosted; smoke: two parallel carts cannot exceed the cap |
| MD-S2-02 | `authorize-capture`, `mark-unknown`, `commit` incl. grant snapshot + `grant_hmac` + outbox (`spend_committed`, `protection_granted`) in one transaction | T: MD-T63..T69, T6B, T75, T77, T83; C23/T23 race test with barrier, repeated K times | D: checkout capture path uses authorize/commit on hosted (pairs S2-01 capture); revoke between approve and capture shows CANCELLED_REVOKED |
| MD-S2-03 | `GET /grants` and `/terms` for revoked mandates; `verify` endpoint; `mandate.integrity_failed` once | T: MD-T05..T09 (tamper + audit cross-check), T66, T67 | D: hosted `verify` shows OK; tamper scene scripted for the video (done via a safe staging fixture, never on the demo DB) |
| MD-S2-04 | Revoke end-to-end with checkout (S2-03): sync authoritative check at use time; `released_reservations`; UI message code `FUTURE_PURCHASES_STOPPED` | T: MD-T60, T63, T65, T6B; E6 Playwright | D: revoke button on hosted UI; copy shows D1(a) sentence labelled "pending confirmation" internally only (never on screen) |
| MD-S2-05 | Outbox relay hardening + sweeper (`/internal/sweep`, expiry events, stale RESERVED release, stuck-capture warnings) wired to scheduled workflow (S2-06) | T: MD-T81, T9C, T9D, T9E | D: `/internal/outbox/flush` + `/internal/sweep` in the scheduled GitHub Actions workflow (not Render cron) |
| MD-S2-06 | Advisory flags thresholds (S priority) and `GET /mandates` list for BFF (S priority) | T: MD-T57, T90 list scoping | D: BFF `buyer-home` unblocked; if not delivered, BFF falls back to direct reads |
| MD-S2-07 | Compose side-by-side CI job: Profile A + Profile B same suite, diff gate (S2-12) | T: deliberately break audience check in A -> CI fails (negative test) | D: compose file documented; Profile A rehearsal #1 (local) |
| MD-S2-08 | Review gates: IDOR suite (T10), T19 JWT, capture-after-revoke, honest-claims grep on render templates (T25), log redaction (T26); record evaluate/reserve latency | T: MD-T90..T96 green | D: security gate S2 recorded in sprint log |
CUT LINE (Oct 23, evening) for mandate: sign, hard blocks, revoke, reserve/authorize/commit, events in audit with `/verify` OK, 5 consecutive clean hosted runs (one after >= 12 h idle), D1 answer obtained or default (a) explicitly accepted. If missed: apply "cut first" list below top-down; never cut the "never cut" items.

## Week 3 (Oct 24-30): integration with resolution, rotation, chaos
| ID | Feature task | Test (T) | Deploy (D) |
|---|---|---|---|
| MD-S3-01 | Resolution integration: `terms_hash` matches resolution `terms_snapshot` hash; `GET /grants?order_id=` at case open and check #3; revoked mandate still serves terms; resolution does not cancel offers inside grants (C12) | T: contract tests with resolution fake and real; MD-T66, T67; TERMS_INVALID path when integrity fails | D: S3 flow on hosted: late order -> offer inside terms from a grant (S3-04/S3-05) |
| MD-S3-02 | Key rotation procedure + `scripts/mandate-keys-in-use` + one drill on hosted staging/demo | T: MD-T11 | D: dated drill record; runbook in `docs/` (names only) |
| MD-S3-03 | Chaos subset on mandate PRs: C14 (mandate down), C16, C21, C22, C23; lock-timeout and crash-mid-txn injections | T: MD-T78, T75, T9C..T9E; PR gate includes the subset | D: nightly chaos job on compose |
| MD-S3-04 | Seed + demo reset: `scripts/seed_demo.py` through the API (real hash/HMAC), reset leaves chain verifiable, new mandate ids per reset (S3-10, S2-09) | T: seed idempotent; reset then `/verify` OK; no SQL-inserted mandates | D: nightly reset workflow includes mandate seed |
| MD-S3-05 | Profile A parity hardening: mandate as separate container, HTTP+JWT; cold start timing recorded | T: full suite on A; MD-T93 (T14) | D: compose rehearsal #2; timings in sprint log |
| MD-S3-06 | Neon pooled-endpoint concurrency run on hosted DB (MD-T7B full) and decision locked | T: MD-T7B repeated | D: config fixed (`PS_MANDATE_DATABASE_URL` choice) |
| MD-S3-07 | Doc/UI wording support: render text final review with UX research findings (tests A/B findings); only template copy changes (bump `render_version` if text changes) | T: MD-T20, T24 golden updated | D: copy deployed; mandate screen items from usability checklist rerun |

## Week 4 (Oct 31-Nov 6): hardening, docs, soak, freeze
| ID | Feature task | Test (T) | Deploy (D) |
|---|---|---|---|
| MD-S4-01 | Hardening: rate limits for preview/sign (with gateway), body size caps, stricter error mapping, `PS_MANDATE_SIGNING_ENABLED` kill switch test | T: MD-T94, T97; kill switch denies signing but not revoke/read | D: deploy; switch documented in runbook |
| MD-S4-02 | Docs: `services/mandate/README`, honest-claims section (demo-grade HMAC, no non-repudiation, D1 status), audit-compare "verify" walkthrough for judge guide, rotation runbook | T: T25 grep over README and judge guide; fresh-clone run of the mandate scenes | D: docs merged by Nov 5 (copy freeze) |
| MD-S4-03 | Soak: 10 consecutive full hosted runs, one after 24 h idle, one with LLM failing; record zero invariant violations in the ledger (DB audit query: `spent+reserved<=max`, no `RELEASED` with capture, no `CAPTURING` stuck) | T: soak script + results log; MD-T70 once more on hosted | D: scheduled 6-hourly smoke continues to Dec 21 (includes sign -> release) |
| MD-S4-04 | Review: external-style pass by Code Reviewer / AppSec agent on canon, HMAC, nonce, locks, grants; fix sev-1/2 | T: new tests for every finding | D: fixes deployed before Nov 6 |
| MD-S4-05 | Free-tier re-check (Nov 1): Render hours, Neon compute hours, pooled-endpoint behavior unchanged | T: warm-up + smoke | D: adjust pings; note in `docs/gates.md` |
| MD-S4-06 | Freeze prep (Nov 5-6): lock `render.v1`/`canon.v1`/`mandate.v1`; confirm D1 final; final migration head; tag candidate | T: full suite on A and B; DoD checklist (test-plan sec 5) | D: Nov 6 evening freeze; after that only config hotfixes and sev-1/2 fixes, no schema change |

## Nov 7-10 (freeze phase, mandate)
- Bug fixes only with a test + hosted smoke; no refactors; no new versions of `schema`/`render`.
- Nov 7-8: record mandate scenes on warmed hosted env (sign with plain text, over-cap block, revoke, tamper detected via `/verify` vs audit chain); backup clip.
- Nov 9: code freeze tag; fresh-clone check; gitleaks full history; rotate demo keys only if exposed (rotation drill already done).
- Nov 10: submit; keep smoke running; note dated TODOs for Render/Neon limits.

## What to cut first (ordered; consistent with sprint-plan cut list, mandate items only)
1. Re-attestation after key compromise (REQ-MD-027) and WebAuthn (REQ-MD-028): never built unless spare time; runbook says "reset demo mandates".
2. Advisory flags (REQ-MD-024): evaluate returns `advisory_flags: []`.
3. `GET /mandates` list (BFF `buyer-home` falls back to direct reads).
4. `GET /mandates/{id}/verify` public route: keep the internal check, drop the public endpoint; the tamper scene is then shown with a test/staging script (weakens the judge-visible "verify" moment: say so).
5. Expiry sweeper loop (REQ-MD-023): lazy read-time expiry still correct; stale RESERVED release happens lazily on touch.
6. Previous-key verify-only support and rotation drill (REQ-MD-021): documented procedure only; disclose "not drilled".
7. `mark-unknown` and `CAPTURE_UNKNOWN` polish: collapse into `CAPTURING` with checkout reconcile calling release(NOT_CAPTURED) or commit (keeps the safety property, fewer states).
8. Profile A hosted rehearsal (sprint-plan cut item 2): compose only; keep CI side-by-side as nightly instead of PR gate only as a last resort (checkout cut item 6 does the same).
Never cut: signed immutable mandate with canonical hash + HMAC and plain-text hash check; deterministic closed hard-block list; revoke with row-locked ordering vs authorize; row-locked cap (reserve/commit) and the DB CHECK; grant snapshot (earned protection); nonce/idempotency; deny-by-default authz and IDOR tests; honest labels; secrets hygiene. If cumulative-cap accounting must shrink (checkout cut item 5 allows per-order cap fallback), the fallback is stated on screen in the demo and the concurrency claim is dropped from the video; mandate still never claims what the test suite does not prove.

## Dependencies to track
- checkout: adopt reserve -> authorize-capture -> commit/release calls; stop `committed_minor`; accept new reason codes; map any non-2xx to no-capture (C2, C8).
- api-gateway: routes for preview/verify/list; keep ledger and evaluate unexposed; CSRF single-use purposes `mandate_sign`, `mandate_revoke`.
- audit: accept three additive mandate event types; chain `mandate_hash` for the independent compare.
- resolution: grants/terms API, no cancel of offers inside grants on revoke (C12), `UNSUPPORTED_TERMS`/`TERMS_INVALID` mapping.
- shopping-agent: summary endpoint shape (numeric fields trusted; `intent_text` untrusted data).
- web: show `screen_text` verbatim, echo `screen_text_hash`, "waking server" state, revoke message wording (needs D1 confirmation), sandbox banner.
- User: D1 decision (by Oct 16 ideally, no later than copy freeze Nov 5); D7 demo values (bounds, deliver-by days); secret-naming preference (spec C5).
