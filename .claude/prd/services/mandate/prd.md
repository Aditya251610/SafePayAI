# mandate: PRD

Date 2026-10-10. Labels: **V** verified, **VC** vendor/secondary claim, **I** inference/assumption. Stack: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic (ADR-002). Slug `mandate` (service-map.md). Companion docs: spec.md, api.md, deployment.md, test-plan.md, sprint-tasks.md.

## 1. Role
- The authority on what an agent may buy and what protection the buyer pre-authorized. It is the hero artifact judges inspect.
- Creates, stores, verifies, revokes and expires buyer-signed mandates. "Signed" means server HMAC over a canonical hash (demo-grade). It is NOT a buyer-held-key signature (V, design choice; auth-gateway.md sec 4.1).
- Runs deterministic `evaluate(cart)`: hard blocks vs advisory flags. No LLM, no catalog dependency, no PayPal credentials.
- Owns the cumulative spend counter (`spent_minor`, `reserved_minor`) and the per-order protection grants.
- Emits `mandate.*` events (outbox, ADR-003) for audit, checkout, resolution.

## 2. Users and callers
| Caller | Uses it for |
|---|---|
| buyer (via api-gateway) | preview text, sign, view, revoke |
| merchant / reviewer (via gateway) | read-only summary (no mutation) |
| checkout (service) | evaluate, reserve, authorize-capture, commit, release |
| resolution (service) | read protection terms and grants (also for revoked mandates) |
| shopping-agent (service) | read-only summary (merchants, remaining cap, intent, expiry) |
| audit (service) | receives events only |
| judges | read the plain-language text, see a widened/tampered mandate refused |

## 3. Requirements
Priority: M = must for demo, S = should, C = could. Each REQ maps to tests in test-plan.md.

| ID | P | Requirement |
|---|---|---|
| REQ-MD-001 | M | Create a mandate only from an authenticated buyer; `buyer_id` comes from the internal token, never the body. |
| REQ-MD-002 | M | Mandate terms are immutable after signing; any change is a new mandate with a new id. DB trigger blocks UPDATE of term columns. |
| REQ-MD-003 | M | Canonical JSON (`canon.v1`, integers only, sorted keys, NFC, UTC `Z` timestamps), SHA-256 `mandate_hash`, HMAC-SHA256 with `key_id`. |
| REQ-MD-004 | M | Server renders the plain-language text (`render.v1`); client must echo `screen_text_hash`; mismatch is rejected. |
| REQ-MD-005 | M | Single-use nonce (TTL), consumed atomically in the same transaction as the insert; replay rejected. |
| REQ-MD-006 | M | `Idempotency-Key` on `POST /mandates`: same key + same body returns the original; same key + different body is a 409. |
| REQ-MD-007 | M | Integrity (recompute hash, verify HMAC) on every evaluate/reserve/authorize; failure is a hard block `MANDATE_INTEGRITY_FAILED`. |
| REQ-MD-008 | M | State machine active / exhausted / revoked / expired with fixed precedence (revoked > expired > exhausted > active). Expiry is computed at read time (no sweeper dependency for correctness). |
| REQ-MD-009 | M | `evaluate` is pure (no writes) and returns `ALLOW` or `BLOCK` + `hard_blocks[]` + `advisory_flags[]`; fail closed on any unknown input. |
| REQ-MD-010 | M | Hard-block list is closed and enumerated (spec sec 6); advisory flags can never turn a BLOCK into ALLOW, and AI results are not an input. |
| REQ-MD-011 | M | Revoke is owner-only, idempotent, takes effect on the next read of the mandate row (stop wins), emits `mandate.revoked`. |
| REQ-MD-012 | M | Spend reservation under a row lock: `spent_minor + reserved_minor + new <= max_total_minor` always; DB CHECK as backstop. |
| REQ-MD-013 | M | Reservation lifecycle RESERVED, CAPTURING (point of no return), CAPTURED, RELEASED, CAPTURE_UNKNOWN; every transition idempotent. |
| REQ-MD-014 | M | Revoke vs in-flight order follows the "earned protection" rule (spec sec 8); marked NEEDS USER CONFIRMATION. |
| REQ-MD-015 | M | Protection grant snapshot created at capture commit (terms copied, tied to `mandate_hash`); later revoke or expiry of the mandate does not alter it. |
| REQ-MD-016 | M | Protection terms validated at signing: refund cap <= max total and <= configured ceiling; deliver-by days within configured bounds. |
| REQ-MD-017 | M | Events via transactional outbox: `mandate.signed`, `mandate.revoked`, `mandate.expired` (service-map) plus proposed additive events (spec sec 11). No `intent_text` in events, only hashes. |
| REQ-MD-018 | M | Every endpoint denies by default: internal JWT with `aud=mandate`, role/scope check, ownership check (404 for non-owner). |
| REQ-MD-019 | M | Uniform error model with stable codes; no stack traces. |
| REQ-MD-020 | M | Server-side validation: `extra=forbid`, length caps, reject control and bidi characters in free text, reject floats. |
| REQ-MD-021 | S | Key rotation with `key_id`; previous key verify-only until no live mandate or grant references it. |
| REQ-MD-022 | S | `GET /mandates/{id}/verify` re-checks integrity and returns the hashes for third-party comparison with the audit chain. |
| REQ-MD-023 | S | Expiry sweeper emits `mandate.expired` once and releases stale RESERVED spends; callable by cron and in-process. |
| REQ-MD-024 | S | Advisory flags (near cap, expires soon, multi-merchant) with config thresholds. |
| REQ-MD-025 | M | `/healthz`, `/readyz`, JSON logs with `trace_id`; secrets and `intent_text` never logged. |
| REQ-MD-026 | M | Runs identically as its own process (Profile A) and mounted in `core` (Profile B); same tests pass in both (CI side-by-side). |
| REQ-MD-027 | C | Re-attestation under a new key after compromise (spec sec 10.4). |
| REQ-MD-028 | C | WebAuthn device-bound approval (stretch in auth-gateway.md); not claimed as non-repudiation. |

## 4. Non-goals
- Pricing, catalog lookups, item recommendation, intent-fit judgement (LLM).
- Refund policy, refund amounts beyond the pre-authorized cap, refund execution, case state.
- Buyer-held-key signatures, non-repudiation, legal binding, KYC, real identity.
- Editing a mandate in place; multi-currency; per-merchant caps (all I, not needed for the demo).
- Restoring budget on refund (spent is gross and monotonic; see spec open question Q7).

## 5. Success metrics (no invented numbers)
| Metric | Target | Label |
|---|---|---|
| Hard-block codes with at least one failing-fixture test each | 100% of the closed list | V once tests exist |
| Concurrency test: N parallel reserves never exceed the cap | 0 violations over repeated runs in CI | V once tests exist |
| Mutated stored mandate (any term column) detected on next use | 100% of mutation fixtures | V once tests exist |
| Widening and replay attempts (cap, allowlist, expiry, nonce reuse) rejected | 100% of fixtures | V once tests exist |
| Same suite green in Profile A and Profile B | required for done | V once CI exists |
| Evaluate latency | measure in S2 and record; no target pre-committed | I |
| Judge-visible: demo shows widened/tampered mandate refused and plain text matches signed hash | in the video script | I |

## 6. Risks
| Risk | Mitigation |
|---|---|
| HMAC key is server-held: server compromise forges mandates | Disclosed; audit chain stores `mandate_hash` independent of the key; no non-repudiation claim |
| Screen text hash proves the server-rendered text, not what pixels the buyer saw | Disclosed; UI shows exactly the server text; no "buyer saw X" claim |
| Revoke-vs-protection semantics wrong for product | Marked NEEDS USER CONFIRMATION; behavior is one config-free code path plus template version, cheap to flip |
| Spend counter drift if checkout crashes between steps | Reservation TTL + CAPTURE_UNKNOWN + reconcile calls; spent only moves on commit |
| Cold start of `core` on Render free (about 1 min wake, V per deployment-zero-cost.md) hits the sign or checkout click | Warm-up script, edge fan-out health check, pinger on edge |
| Neon pooled connections vs row locks | Transaction-scoped locks only (`FOR UPDATE`), no session advisory locks; test on the real host (I) |
| Drift between docs (orchestrator/policy names) and service-map | Followed service-map; conflicts listed in spec sec 12 |
| Time: mandate is on the critical path of every other service | Contract-first OpenAPI by end of week 1 so checkout can mock it |
