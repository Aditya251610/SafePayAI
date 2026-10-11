# audit - test plan

Labels: V verified, VC vendor claim, I inference/unverified. Date 2026-10-10. References test IDs from `test-strategy.md` (root) and REQ-AU-* from prd.md; implements T17 (threat-model), S-suite N/A (audit has no PayPal calls). No invented numeric targets beyond what prd.md/spec.md already state.

## 1. Append-only enforcement test (REQ-AU-010..012; test-strategy.md T17, L3)
- Layer: L3 integration, ephemeral Postgres schema with real grants applied (data-architecture.md sec 11 - must run against real Postgres, not SQLite, to exercise role grants and triggers).
- Setup: connect as `audit_app` (runtime role, INSERT+SELECT only on `entries`/`verify_runs`/`head_exports`, no UPDATE/DELETE/TRUNCATE grant - spec.md sec 8).
- Cases (map to prd.md "metric: Append-only enforced", target 100% of attempts denied):
  1. `UPDATE audit.entries SET payload = ... WHERE seq = 1` as `audit_app` -> expect permission-denied error (grant-level denial), not a trigger error (grants deny before the trigger fires).
  2. `DELETE FROM audit.entries WHERE seq = 1` as `audit_app` -> permission denied.
  3. `TRUNCATE audit.entries` as `audit_app` -> permission denied.
  4. Repeat 1-3 as `audit_owner`/`mig_audit` with grants intact but triggers enabled -> expect the BEFORE UPDATE/DELETE/TRUNCATE trigger (`audit_is_append_only`) to raise, proving defense-in-depth even for an elevated role that still has grants.
  5. Assert `audit_app` has no `TRIGGER` privilege and is not the table owner, so it cannot `ALTER TABLE ... DISABLE TRIGGER` (spec.md sec 8) - attempt it and expect denial.
  6. No code path exists that issues UPDATE/DELETE/TRUNCATE against `entries` (static check: grep service code for those verbs against the table; REQ-AU-001).
- Pass/fail: every attempt in 1-5 denied; test fails (Sev1, money/safety-adjacent per test-strategy.md sec 14) if any mutation succeeds.
- CI placement: L3, every push (test-strategy.md sec 2); mandatory regardless of coverage floor (test-strategy.md sec 10: "100% of hard-block codes" analog for audit = 100% of denial paths covered).

## 2. Chain-verify test (REQ-AU-040, REQ-AU-045; spec.md sec 7)
- Layer: L1 (pure hashing/canonicalization logic) + L3 (against real Postgres with the append path).
- Golden-vector check (L1): run committed vectors under `services/audit/tests/vectors/` through `app/chain/canonical.py` and `hashing.py`; byte-for-byte canonical output and SHA-256 hash must match the committed expected values (spec.md sec 4) - catches canonicalization drift (risk R5 in prd.md) between writer and verifier before any DB is involved.
- Happy path (L3): append N events (N small, e.g. the catalog's full type list per REQ-AU-030) via `POST /internal/events[/batch]`; call `GET /verify`; expect `{"ok": true, "checked": N+1 incl. genesis, head_seq, head_hash}` with zero mismatches.
- Genesis check: fresh schema with only the migration-inserted genesis row -> `GET /verify` returns `ok: true, checked: 1`.
- Negative reason-code coverage (spec.md sec 7, api.md sec 3) - one sub-test per `reason`:
  - `HASH_MISMATCH`: as owner, edit one byte of `canonical` on a non-head row, bypass/disable the trigger first (spec.md sec 12 step B) -> verify returns this row's seq and reason.
  - `PREV_MISMATCH`: edit `prev_hash` on a row (owner, trigger disabled) -> detected.
  - `SEQ_GAP`: delete a middle row as owner -> detected (also likely surfaces as `PREV_MISMATCH` depending on which row is checked first; assert at least one of the two expected codes per spec.md sec 12 step 3).
  - `PAYLOAD_MISMATCH`: edit only the `payload` JSONB copy column, leave `canonical` untouched -> detected distinctly from `HASH_MISMATCH` (spec.md sec 2.1 "verify checks derived == parsed canonical").
  - `GENESIS_MISSING`: on an empty/misconfigured table, appender refuses (spec.md sec 3 step 4) and verify also reports this reason if reached directly.
  - `CHAIN_ID_MISMATCH`: row with a different `chain_id` value injected (owner) -> detected.
  - `ANCHOR_HASH_MISMATCH` / `ANCHOR_SEQ_BEYOND_HEAD`: call `GET /verify?anchor_seq=&anchor_hash=` against a known-good head, then again after a tail truncation (spec.md sec 12 step 3 "truncate tail") -> `ANCHOR_SEQ_BEYOND_HEAD`; against a tampered-but-rehashed chain (spec.md sec 12 step C, "sophisticated attacker") -> plain verify PASSES but anchor check FAILS, demonstrating the documented honest limit (spec.md sec 11).
- Idempotency/dedup check (REQ-AU-004): push the same `event_id` twice -> second call returns `{"seq": <same>, "duplicate": true}`, no new row, verify `checked` count unchanged by the duplicate.
- Pass/fail: every negative case returns the exact documented `reason` code (api.md sec 3); any case returning `ok: true` when it should fail is Sev1 (audit chain broken, test-strategy.md sec 14).

## 3. Concurrent-writer test (REQ-AU-003; spec.md sec 3 option B; test-strategy.md C19/C20 analog for audit)
- Layer: L3, real Postgres (advisory locks must be exercised against the actual pooled/PgBouncer path, not a fake).
- Setup: N parallel append requests (N=20, matching test-strategy.md's existing concurrency convention for refund tests at N=20) each with a DISTINCT `event_id`, fired concurrently at `POST /internal/events` against the pooled endpoint (not direct), to also prove `pg_advisory_xact_lock` works under PgBouncer transaction mode (spec.md sec 3 option B note, VC - this test is what turns that VC into a V).
- Expected: all 20 appended with no error beyond possible bounded retries (`PS_AUDIT_APPEND_MAX_RETRIES`, config); resulting `seq` values form a gapless contiguous run with no duplicates; `UNIQUE(prev_hash)` and `UNIQUE(row_hash)` never violated (spec.md sec 2.1 fork guard); `GET /verify` after the run returns `ok: true` with `checked == genesis + 20`.
- Fork-attempt variant: two requests racing for the SAME next `seq`/`prev_hash` pair (simulated by holding one txn open past the head-read of another, if the test harness can force this) -> exactly one commits, the other serializes behind the advisory lock and gets the next slot, or hits the trigger's linkage check and is rejected/retried; zero forks (prd.md success metric "No forks under concurrency": zero forks).
- Batch variant: `POST /internal/events/batch` with N events in one call -> one advisory lock, one commit, gapless `seq` run for the whole batch (api.md sec 1).
- Pass/fail: any duplicate `seq`, any two rows sharing a `prev_hash`, or `verify` reporting `SEQ_GAP`/`PREV_MISMATCH` after this test is Sev1.
- Also records (not pass/fail, per spec.md sec 3 "Throughput on a free Postgres"): append p50/p95 latency and batch-vs-single-append timing on Neon free, matching spec.md's T-AU-13 intent - recorded only, no invented target.

## 4. Tamper-detection test on a scratch copy (REQ-AU-051; spec.md sec 12, verbatim procedure)
- NEVER run against production/`main` branch data. Scratch copy = a Neon branch of the audit schema, or a local docker Postgres loaded from `pg_dump` (spec.md sec 12 step 1).
- Guard: `scripts/tamper_demo.py --scratch-url ...` refuses to run if the target host matches the configured production host, or if `PS_AUDIT_ENV=prod` (spec.md sec 12 step 5) - this guard itself is a test case (attempt to run it against a URL string matching the prod pattern -> refuses).
- Step A (app role cannot mutate): connect as `audit_app` to the scratch DB, attempt UPDATE/DELETE/TRUNCATE -> denied; assert the denial also names the trigger (where applicable) to prove triggers AND grants both fire (overlaps test 1 above, run here too since it is part of the documented demo script).
- Step B (owner can, verify catches it): as owner, `ALTER TABLE entries DISABLE TRIGGER USER;` then mutate one payload field / amount in `canonical` -> `GET /verify` on the scratch service returns `HASH_MISMATCH` at that seq. Variants per spec.md sec 12 step 3: edit only the `payload` copy column -> `PAYLOAD_MISMATCH`; delete a middle row -> `SEQ_GAP`/`PREV_MISMATCH`; swap two rows; truncate the tail -> verify reports `ok` but the anchor check reports `ANCHOR_SEQ_BEYOND_HEAD`.
- Step C (sophisticated attacker, the honest-limit demonstration): a script recomputes ALL hashes after the edit using the public algorithm -> plain `GET /verify` now PASSES; `GET /verify?anchor_seq=&anchor_hash=` against a previously-exported head (taken before the edit) FAILS. This is the moment the demo/docs show openly, not hide (spec.md sec 12 step 4; prd.md non-goal "no non-repudiation claim").
- Output: `scripts/tamper_demo.py` prints a table of mutation -> detected? -> by which check, matching prd.md success metric "Tamper detection: every mutation detected by verify or anchor check" - the table itself is the test evidence artifact, attached to the test report.
- Pass/fail: Step A must deny 100%; Step B mutations must ALL be caught by plain verify; Step C must be caught ONLY by the anchor check (plain verify passing in Step C is expected and correct, not a failure - this is the one case where "verify: ok" is the documented, honest outcome).

## 5. Additional coverage (REQ-AU-005, REQ-AU-020..022, REQ-AU-030..032; event/actor/redaction)
- Schema/redaction (L1+L2, test-strategy.md sec 6 "injection corpus" pattern reused): feed secret-looking strings (`Bearer `, `sk-`, `eyJ`-prefixed JWT, `client_secret`, raw emails/names) into every per-type payload schema -> all rejected `SECRET_PATTERN_REJECTED`/`UNKNOWN_FIELD` (REQ-AU-005, spec.md sec 6 "Redaction rules").
- Actor allowlist (L3, REQ-AU-020/021): a caller token for `producer=X` attempting to emit an `actor_type` not in X's allowed set (spec.md sec 5 table) -> `403 ACTOR_NOT_ALLOWED`; `producer` field not matching verified token `sub` -> `403 PRODUCER_MISMATCH`; nothing written in either case (api.md sec 1).
- Float-forbidden / check-array-shape (REQ-AU-031): payload containing a float -> `422 FLOAT_FORBIDDEN`; a `REFUND_COMPLETED`-family event with a `checks[]` array not length 9 or non-contiguous `n` -> `422 CHECKS_ARRAY_INVALID` (spec.md sec 6 "Check results").
- Event-type coverage (REQ-AU-030, prd.md success metric "Event coverage"): CI assertion that every `event_type` listed in spec.md sec 6 has at least one L2 producer schema test and one L3 round-trip append test; full catalog coverage is also asserted once per L4/e2e demo run (test-strategy.md L4).

## 6. CI side-by-side (how these land in the pipeline, per test-strategy.md sec 2/8)
| test (this doc) | layer | runs | sprint gate (test-strategy.md sec 8) |
|---|---|---|---|
| Append-only enforcement | L3 | every push | S1 ("L3 audit trigger + role (T17 basic)" required to exit S1) |
| Chain-verify (golden vectors) | L1 | every push | S1 |
| Chain-verify (happy path + reason codes) | L3 | every push | S1 (basic) -> full reason-code matrix by S2 |
| Concurrent-writer | L3 + L6 | PR to main, nightly | S2/S3 (concurrency suite pattern, aligned to T1/T20 cadence) |
| Tamper-detection (scratch) | manual + nightly | nightly, pre-recording, and re-run at S4 (test-strategy.md sec 8: "audit tamper test re-run on Neon" required for S4 exit) | S4 |
| Redaction / actor allowlist / schema | L1 + L2 | every push | S1 (redaction), S2 (allowlist, as part of event schema tests) |
| Event-type coverage | L4 | PR to main, nightly | S2 (recorded), full by S3/S4 |
- Flake policy: money-path-adjacent invariant tests here (append-only, chain-verify reason codes, concurrent-writer) follow test-strategy.md sec 9 - no sleep-based assertions, cannot be quarantined if they touch chain integrity (treated like T1/T5/T20: "fix or block merge").
- Coverage floor: audit is not in the explicit money-path list (mandate/checkout/resolution/paypal-adapter) in test-strategy.md sec 10, so its default floor is >=70% lines; however append-only/chain tests are MANDATORY regardless of coverage percentage (test-strategy.md sec 10 "mandatory regardless of coverage" pattern extended here to 100% of denial paths and 100% of verify reason codes).

## 7. Definition of done
- All five test categories above (sections 1-4, plus 5) exist in `services/audit/tests/` with passing CI runs on the stated layer.
- `services/audit/tests/vectors/` golden vectors committed and green.
- `scripts/tamper_demo.py` runs clean against a scratch Neon branch or local docker Postgres and produces the mutation-detection table; script's prod-guard verified by a dedicated negative test.
- `scripts/verify_chain_standalone.py` (stdlib-only) independently verifies an exported NDJSON chain and agrees with the service's own `GET /verify` result on the same data (cross-check that the "third party can verify without our service" claim, auth-gateway.md sec 9, actually holds).
- Grants-matrix CI test (data-architecture.md sec 4/11) passes: `audit_app` has exactly INSERT+SELECT on the three audit tables and nothing else, no cross-schema access.
- EXPLAIN ANALYZE recorded once (data-architecture.md sec 13 checklist item) for: chain append (lock + head-select + insert), and the main `GET /entries` grid query; Seq Scan acceptable at demo table size if documented (spec.md sec 9).
- Every REQ-AU-0xx in prd.md sec 3 has at least one test case referenced above; every prd.md sec 5 success metric has a corresponding pass/fail or recorded-value test.
- No Sev1 open (test-strategy.md sec 14) in any of the above before this service is marked done for its sprint.
