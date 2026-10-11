# audit - PRD

Labels: V verified, VC vendor/secondary claim, I inference/unverified. Date 2026-10-10. Owner: Database Optimizer. Sources: context brief, service-map.md, adr.md (these win on conflict), overview.md, auth-gateway.md, threat-model.md, deployment-zero-cost.md. Conflicts are recorded in spec.md section 14.

## 1. Purpose
`audit` is an append-only, hash-chained, tamper-EVIDENT log of what SafePayAI did and who (or what) caused it: mandate signed, cart proposed/blocked, order created/captured, tracking signals, cases, offers, approvals, refunds, AI calls (model id + prompt version + input hash). It exists so a judge (or the buyer) can see a reasoned trail, press "verify chain", and see tampering caught. It is an observer: it is NOT on the money path and never decides anything (service-map).

## 2. Users and jobs
| user | job |
|---|---|
| Buyer | See the trail for MY mandate/orders/cases (own rows only). |
| Merchant (shared login) | See order/shipment/case/refund trail. |
| Reviewer / operator | See everything; run verify; export head; run tamper demo on a scratch copy. |
| Judge / third party | Verify the chain and compare the exported head hash with the one pasted in the submission. |
| Other services | Push events (HTTP, service token). Never read or write by SQL. |

## 3. Requirements
Priority: P0 must for demo, P1 should, P2 could.

### Append and chain
- REQ-AU-001 (P0) Entries are only added via `POST /internal/events` (and the batch form); no update/delete path exists in code.
- REQ-AU-002 (P0) Global single chain: each entry stores `prev_hash` and `row_hash` computed over canonical content (spec section 4). Genesis entry is created by migration.
- REQ-AU-003 (P0) Gapless `seq`; two concurrent writers can never fork the chain (advisory lock plus unique `seq` and unique `prev_hash`, spec section 3).
- REQ-AU-004 (P0) Idempotent on `event_id`: a duplicate push returns the existing `seq`, never a second row (outbox is at-least-once, ADR-003).
- REQ-AU-005 (P0) Reject payloads that do not validate against the per-type schema (unknown fields rejected). No secrets or PII in payloads; redaction test.

### Enforcement
- REQ-AU-010 (P0) App DB role has INSERT and SELECT only on the chain table. UPDATE/DELETE/TRUNCATE denied by grants AND blocked by triggers (defense in depth).
- REQ-AU-011 (P0) Table owner/migrator credentials are not present in the running service env.
- REQ-AU-012 (P0) A BEFORE INSERT trigger rejects any row whose `seq`/`prev_hash` is not the current head's successor.

### Actor stamping
- REQ-AU-020 (P0) Every entry has `actor_type`, `actor_id`, `auth_method`, `request_id` (plus `trace_id`). Values originate from verified tokens at the producer; audit validates them against the verified caller token and a per-event-type allowlist and REJECTS disagreement (auth-gateway section 7).
- REQ-AU-021 (P0) Callers cannot self-assert an actor class their service is not allowed to emit (e.g. only `mandate` may emit buyer-attributed MANDATE_SIGNED).
- REQ-AU-022 (P1) Merchant entries say `merchant_shared`; reviewer entries say `reviewer_selfasserted` (names unverified). Never presented as individual accountability.

### Event coverage
- REQ-AU-030 (P0) Catalog in spec section 6 is covered: MANDATE_*, CART_PROPOSED/CHECKED/BLOCKED, ORDER_*, TRACKING_*, CASE_*, OFFER_*, APPROVAL_*, REFUND_*.
- REQ-AU-031 (P0) Refund events carry mandate hash, proposal_hash, PayPal ids, request ids, the 9 ordered check results.
- REQ-AU-032 (P0) AI events carry model id, prompt version, input hash, output hash; never labelled as a decision-maker for money.

### Verify, export, read
- REQ-AU-040 (P0) `GET /audit/verify` recomputes the whole chain (bounded by the head at call start) and returns `ok` or the first bad `seq` with reason (HASH_MISMATCH, PREV_MISMATCH, SEQ_GAP, PAYLOAD_MISMATCH, GENESIS_MISSING).
- REQ-AU-041 (P0) `GET /audit/head` returns `{seq, row_hash, chain_id, count, recorded_at}` and a one-line paste string, so the head can be anchored outside the DB (e.g. in the submission text or a repo file).
- REQ-AU-042 (P0) `GET /audit/entries` serves AG Grid server-side row model: filter, sort, paging, role-scoped rows (buyer sees only own).
- REQ-AU-043 (P1) Head export is Ed25519-signed by an audit signing key (public key in repo) so past anchors cannot be forged by a DB-only attacker.
- REQ-AU-044 (P1) Scheduled verify (free cron) and failure surfaced to the operator; kill-switch trip is owned by the freeze owner (spec section 14).
- REQ-AU-045 (P1) Verify from a pasted anchor: `GET /audit/verify?anchor_seq=&anchor_hash=` confirms the row at `anchor_seq` still has that hash (detects tail truncation and history rewrite relative to the anchor).

### Operability
- REQ-AU-050 (P0) `/healthz` (no DB), `/readyz` (DB reachable, cold-start tolerant), structured JSON logs with request_id.
- REQ-AU-051 (P0) Tamper demo script runs on a scratch copy (never production data) and shows verify failing.
- REQ-AU-052 (P1) Producers keep working when audit is down (outbox); audit exposes lag so the UI can show "audit catching up".

## 4. Non-goals (explicit)
- NO non-repudiation claim. HMAC mandates are demo-grade, buyer holds no key; the log shows what the SYSTEM recorded, not that a person cannot deny it.
- NO "immutable", "tamper-proof", "compliant", "legally binding" wording. Use "tamper-evident".
- Not protection against the DB owner/superuser or platform operator: they can rewrite rows and recompute the chain (spec section 11).
- Not a SIEM, not analytics, not a message broker, not event replay for other services.
- No per-merchant accountability (single shared merchant login, disclosed).
- No storage of secrets, card/PII data, raw prompts, raw buyer free text (hashes only).
- Does not trip the refund freeze itself (no write access outside its schema).

## 5. Success metrics (no invented targets; measured values recorded in test results)
| metric | how measured | target |
|---|---|---|
| Append-only enforced | test-plan T-AU-01..04 all pass as app role | 100% of attempts denied |
| Tamper detection | tamper-demo mutations (edit payload, edit hash, delete row, reorder, truncate-vs-anchor) | every mutation detected by verify or anchor check |
| No forks under concurrency | concurrent writers test: verify ok, seq gapless | zero forks |
| Event coverage | every catalog type emitted at least once in e2e demo run | all types in section 6 of spec |
| Idempotency | duplicate pushes of one event_id | exactly one row |
| Append latency and verify time | measured on Neon free during test-plan run | record only; target unknown (I) |
| Judge comprehension | time to find the verify button and see result in the demo | demo script shows it inside the 3-minute video (shot list owned elsewhere) |

## 6. Dependencies
- Producers' outbox relays (ADR-003) push to `POST /internal/events`; auth via internal service JWT (auth-gateway section 3).
- api-gateway exposes `/audit/verify`, `/audit/records` style routes to the web (names reconciled in api.md).
- Neon Postgres, `audit` schema, separate roles (ADR-004).
- web: AG Grid audit view (sponsor prize alignment is a decision outside this doc; only one sponsor prize per project, brief).

## 7. Risks
| # | risk | impact | mitigation | residual |
|---|---|---|---|---|
| R1 | Superuser/owner rewrites and re-hashes whole chain | log silently falsified | external head anchor, signed heads (REQ-AU-043), honest wording | Medium: undetectable without an anchor older than the rewrite |
| R2 | Neon role model (owner is not a true superuser, I) behaves differently than assumed | INSERT/SELECT-only role cannot be built | spike on day 1 (sprint task S1-3); fallback is triggers plus app-level guard and a lowered claim | Low once spiked |
| R3 | Chain contention or lock stalls on cold Neon | slow appends, outbox backlog | one short txn under advisory lock, batch append, retries absorbed by outbox | Low at demo volume (hundreds of events, overview I) |
| R4 | Pooled endpoint (transaction mode) breaks session features | lost locks, prepared-statement errors | use only `pg_advisory_xact_lock`, disable client statement cache | Low, verified in test |
| R5 | Canonicalization drift between writer and verifier | false tamper alarms | single shared function, golden test vectors, version tag in content | Low |
| R6 | Payload leaks secret/PII | public repo/demo exposure | per-type schema allowlist, redaction test, hashes not raw text | Low |
| R7 | Actor field spoofed by a compromised producer | misattributed trail | per-producer allowed actor types, token `sub` must equal envelope producer; honest limit | Medium (producer trusted for the user actor, spec section 5) |
| R8 | Neon compute hours burned by pings or verify loops | DB suspended mid-review | no DB in `/healthz`, verify on demand/cron only in windows | Low |
| R9 | Audit down at demo time | trail incomplete in view | outbox retries, warm-up, lag banner | Low |
| R10 | Tail truncation (delete last N rows as owner) undetectable without anchor | hidden recent actions | anchor head before/after demo; head export each major milestone | Medium |
| R11 | Judges read "audit" as proof | over-claim | UI/README wording "tamper-evident, DB owner can rewrite" | Low |
