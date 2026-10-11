# mandate: test plan

Labels V/VC/I. Stack: pytest + httpx ASGI client, real Postgres (CI service container or testcontainers; never SQLite), Hypothesis for properties, injected clock, fakes generated from committed OpenAPI for neighbors. IDs: `MD-Txx` are local; `T*`, `C*`, `E*` refer to `test-strategy.md` (T4 mandate hard blocks/HMAC tamper/nonce replay/AI cannot override; T10 IDOR; T13 secrets; T14 direct call without JWT; T19 JWT; T21 no stack traces; T22 server derives money fields; T23 revoke race; T24 audit completeness; T25 honest claims; T26 log redaction; C14 mandate down; C16 audit down; C21 duplicate events; C22 cold consumer; C23 revoke between approval and capture; E5 over-cap blocked; E6 revoked mandate blocks confirm). Spec sections: `spec.md`. Parameters (cap, amounts, N) are symbolic fixtures chosen in test config; no product numbers are implied.

## 1. Tiers
| Tier | Runs | Contents |
|---|---|---|
| U unit | every push | canonicalizer, hash, HMAC, render, validators, evaluate, state derivation, reservation state machine (pure parts), advisory/decision separation |
| P property | every push | Hypothesis: hash stability, evaluate monotonicity, state machine under random op order |
| C contract | every push | OpenAPI diff vs `contracts/openapi/mandate.json`; response schemas; event JSON Schemas; consumer smoke vs checkout/resolution fakes |
| I integration | PR + main | real Postgres with real roles/grants/triggers; concurrency tests; outbox; migrations up/down |
| Z chaos subset | money-path PRs | C14, C16, C21, C22, C23 mandate-side plus lock-timeout and crash-mid-transaction injections |
| E2E | PR (stubbed PayPal) + hosted rehearsals | Playwright E5, E6 plus sign/revoke/tamper scenes; hosted smoke after each deploy |
Sandbox PayPal is not needed by mandate tests (mandate has no PayPal calls); the hosted smoke exercises mandate through checkout.

## 2. Cases
P0 = must pass before demo and merge-blocking from the sprint noted in sec 6.

### 2.1 Canonical JSON, hash, HMAC, tamper detection (spec sec 3)
| ID | P | Case | Expected |
|---|---|---|---|
| MD-T01 | P0 | Property: canonical bytes/hash identical under key order, allowlist input order, NFC vs NFD input, kinds order | same hash; different effective terms -> different hash |
| MD-T02 | P0 | Golden vector: fixed terms -> committed expected canonical bytes and hash (`fixtures/canon_v1.json`) | byte-equal; a change fails CI and demands a version bump |
| MD-T03 | P0 | Floats, `Decimal`, exponents, NaN, `true` where int expected, ints beyond 2^53-1 in any field | 422 `VALIDATION_ERROR`; nothing persisted |
| MD-T04 | P0 | Timestamp strictness: offsets, fractional seconds, local time | rejected |
| MD-T05 | P0 | T4 HMAC tamper: with a superuser fixture, mutate each stored term column one at a time (currency, max_total, max_qty, allowlist, intent_text, expires_at, protection parts, policy_version, nonce, created_at, buyer_id, screen_text_hash), then evaluate, reserve, verify | every one -> `MANDATE_INTEGRITY_FAILED` (block / 409 / `integrity:"FAILED"`); `mandate.integrity_failed` emitted once |
| MD-T06 | P0 | Consistent forgery without key: rewrite columns + `canonical_json` + `mandate_hash` together | HMAC check fails -> integrity failed |
| MD-T07 | P0 | Tamper `hmac`, `hmac_key_id` (unknown id), `hmac_alg`, `schema` version | integrity failed (`KEY_UNKNOWN` for unknown id) |
| MD-T08 | P0 | Runtime role cannot UPDATE/DELETE immutable tables; trigger blocks even if grant exists; `max_total_minor` copy in `mandate_spend` immutable | permission/trigger error; row unchanged |
| MD-T09 | P0 | Audit cross-check: after tamper, `GET /verify` shows `mandate_hash` recomputed != hash in the `mandate.signed` audit entry (independent of key) and audit `/verify` chain still OK | demonstrable in the demo script (T24 style) |
| MD-T10 | P0 | Key handling: no key / short key / equal current+previous ids at boot | process not ready; `POST /mandates` refused; no log line contains key bytes |
| MD-T11 | P1 | Key rotation: sign under key A; rotate (A previous); verify OK; sign new under B; drop A while a live mandate or grant uses A | verify OK until A dropped; then `KEY_UNKNOWN` fail closed; `mandate-keys-in-use` lists them first |
| MD-T12 | P2 | Re-attestation (if built): attest only when row hash equals audit-recorded hash | match -> new attestation verifies; mismatch -> quarantined |

### 2.2 Plain-language rendering and text hash (spec sec 4)
| ID | P | Case | Expected |
|---|---|---|---|
| MD-T20 | P0 | Golden render: fixed terms -> committed text fixture | exact text and `screen_text_hash` match |
| MD-T21 | P0 | Client echoes a hash for text it rendered itself (different wording) | 422 `SCREEN_TEXT_MISMATCH` |
| MD-T22 | P0 | Text covers every signed term (property: mutate any term -> text differs, except non-displayed ids) | all money, merchants, expiry, protection, revoke sentence present |
| MD-T23 | P0 | Free text with control, bidi (U+202E), zero-width, newline, BOM, over-length | 422; offending text not echoed in logs |
| MD-T24 | P0 | T25 banned phrases absent from every template and from API error messages | grep list clean |
| MD-T25 | P1 | Money formatting is integer-only (no float rounding) for edge minor-unit values | exact strings |
| MD-T26 | P1 | Insertion safety: intent text containing quotes/markdown/HTML renders as literal text; UI escapes (Playwright) | no injection into screen |

### 2.3 Widening and unauthorized-change attempts (spec sec 10.1, 9.1)
| ID | P | Case | Expected |
|---|---|---|---|
| MD-T30 | P0 | Preview terms X, then sign with larger `max_total_minor` using the same nonce and hash | 409 `NONCE_INVALID` (terms digest mismatch); no mandate |
| MD-T31 | P0 | Same, widening each of: allowlist (extra merchant), expiry, `max_qty_per_line`, `protection.max_refund_minor`, `deliver_by_days`, kinds | each rejected, never stored |
| MD-T32 | P0 | `max_refund_minor > max_total_minor`, above ceiling, `deliver_by_days` below/above bounds, empty kinds, unknown kind | 422 `TERMS_OUT_OF_BOUNDS` |
| MD-T33 | P0 | T22 body contains `buyer_id`, `status`, `spent_minor`, `mandate_hash`, `hmac`, `mandate_id` | 422 `FIELD_NOT_ALLOWED` |
| MD-T34 | P0 | No mutation surface: PATCH/PUT/DELETE on mandates | 405; OpenAPI has none |
| MD-T35 | P0 | Direct DB UPDATE of terms as runtime role, then use | denied; if forced as superuser, MD-T05 applies |
| MD-T36 | P0 | Evaluate widening via cart: extra merchant, qty above cap, currency swap, total below sum of lines | the matching hard blocks (see 2.5) |
| MD-T37 | P1 | `policy_version` echo different from current; `revoke_effect` echo different | 409 `POLICY_VERSION_MISMATCH` / 422 |
| MD-T38 | P1 | Expiry in the past, below min, above max | 422 `TERMS_OUT_OF_BOUNDS` |

### 2.4 Replay, nonce, idempotency (spec sec 10)
| ID | P | Case | Expected |
|---|---|---|---|
| MD-T40 | P0 | T4 nonce reuse: sign succeeds, same nonce again with a new Idempotency-Key | 409 `NONCE_INVALID`; one mandate row |
| MD-T41 | P0 | Expired nonce (injected clock); nonce of another buyer; nonce never issued | 409 `NONCE_INVALID`, one generic message (no oracle) |
| MD-T42 | P0 | Same Idempotency-Key + same body (client retry after timeout) | original 201 body, `Idempotent-Replay: true`, one row, one `mandate.signed` |
| MD-T43 | P0 | Same key + different body | 409 `IDEMPOTENCY_KEY_REUSED` |
| MD-T44 | P0 | N parallel identical sign requests, same nonce, different keys | exactly one mandate; others 409 (PK violation on `nonce_uses`) |
| MD-T45 | P0 | N parallel identical requests, same key | one mandate; all callers get the same body |
| MD-T46 | P0 | Replay of a captured valid request body from a different buyer session | 409 (nonce bound to buyer) |
| MD-T47 | P1 | Rollback leaves no half state: failure after nonce use insert but before commit | nonce still unused, no mandate, no outbox row |
| MD-T48 | P1 | Preview spam: each call issues a nonce; expired nonces garbage-collected by sweeper | bounded table growth; rate limit at gateway (T16 style) |

### 2.5 Evaluate: hard blocks vs advisory (spec sec 6)
| ID | P | Case | Expected |
|---|---|---|---|
| MD-T50 | P0 | One failing fixture per hard-block code: `MANDATE_INTEGRITY_FAILED, MANDATE_REVOKED, MANDATE_EXPIRED, MANDATE_EXHAUSTED, MERCHANT_NOT_ALLOWED, OVER_CAP (including fees in total), UNKNOWN_SKU, QTY_CAP, CURRENCY_MISMATCH, PRICE_MISMATCH, CART_ARITHMETIC_MISMATCH` | `BLOCK` with exactly that code; E5 over-cap path covered in E2E |
| MD-T51 | P0 | Valid cart | `ALLOW`, empty `hard_blocks` |
| MD-T52 | P0 | Several simultaneous problems | all applicable codes in fixed order (except integrity failure, which returns only itself) |
| MD-T53 | P0 | Boundary values: total == remaining (ALLOW), remaining+1 minor unit (BLOCK); qty == cap (ALLOW), cap+1 (BLOCK); `now == expires_at` (expired) | exact |
| MD-T54 | P0 | Malformed cart: empty lines, duplicate SKU lines, qty 0/negative, float, missing field, extra field | 422 `MALFORMED_CART`/`FIELD_NOT_ALLOWED`; checkout fake maps to BLOCK |
| MD-T55 | P0 | T4 AI cannot override: request carrying `intent_fit`/`verdict`/`PASS` | 422 `FIELD_NOT_ALLOWED`; contract test shows no such field |
| MD-T56 | P0 | Property: for any advisory configuration and any flags, `decision` is unchanged; ALLOW iff `hard_blocks == []` | holds |
| MD-T57 | P1 | Advisory flags: `NEAR_CAP`, `EXPIRES_SOON`, `MULTI_MERCHANT` triggered by config thresholds | present, never blocking |
| MD-T58 | P0 | `committed_minor` supplied with a misleading value | ignored; result uses mandate's own counters |
| MD-T59 | P0 | Evaluate has no side effects (DB write count zero, no outbox rows) and responses carry `no-store` | verified |
| MD-T5A | P0 | Evaluate under dependency failure of its own DB | 503; checkout fake blocks (C14 side) |

### 2.6 Revoke, stale-after-revoke race, earned protection (spec sec 8; D1(a) pending user confirmation)
| ID | P | Case | Expected |
|---|---|---|---|
| MD-T60 | P0 | Revoke then evaluate / reserve | `MANDATE_REVOKED` block / 409; E6 (revoked mandate blocks confirm) in E2E |
| MD-T61 | P0 | Revoke idempotent; second call returns original body; one `mandate.revoked` | verified |
| MD-T62 | P0 | Non-owner revoke (T10) | 404; mandate unchanged |
| MD-T63 | P0 | Reserve (RESERVED) -> revoke -> authorize-capture | revoke released the reservation; authorize 409 `MANDATE_REVOKED`; `reserved_minor` back to prior; checkout fake does not capture (C23 / T23) |
| MD-T64 | P0 | Stale-after-revoke race: two threads with a barrier, one `revoke`, one `authorize-capture`, repeated K times | exactly one history: either authorize succeeded and its `authorized_at` is before `revoked_at` (later revoke affects future only), or authorize refused; never authorize succeeding after a visible revoke; never a capture-authorized reservation with `RELEASED` state |
| MD-T65 | P0 | Stale cached ALLOW: `evaluate` ALLOW, then revoke, then `reserve` | reserve refuses; no cache layer in service (assert headers `no-store`) |
| MD-T66 | P0 | Earned protection (D1(a)): authorize -> revoke -> commit | commit succeeds; grant created; `GET /grants` shows `mandate_status: revoked`, `protection_in_force: true`; new carts blocked |
| MD-T67 | P0 | Already captured order; revoke; resolution-side read of terms | `GET /mandates/{id}/terms` and `/grants` still 200 with integrity OK |
| MD-T68 | P0 | Parametrized by `revoke_effect`: v1 `FUTURE_ONLY` asserts the above; test file marks the (b) variant `xfail(strict)` with reason "D1 not chosen" so flipping D1 is a visible test change | present |
| MD-T69 | P1 | Revoke while reservation is `CAPTURING` / `CAPTURE_UNKNOWN` | not released; revoke succeeds; later commit allowed; release only with `NOT_CAPTURED` |
| MD-T6A | P1 | Revoke an expired mandate; revoke an exhausted mandate | expired -> 200 no-op, no event; exhausted -> revoked |
| MD-T6B | P0 | `mandate.revoked` event lag cannot allow spend: consumer down, revoke, then reserve | still refused (sync authoritative; S2-03) |

### 2.7 Concurrent spends and the ledger (spec sec 7)
| ID | P | Case | Expected |
|---|---|---|---|
| MD-T70 | P0 | N parallel reserves (distinct orders), each amount such that only M fit under the cap | exactly M succeed, rest `RESERVATION_REFUSED` `OVER_CAP`; `spent + reserved <= max` asserted from DB after each run; repeat K times; real Postgres, pooled connections |
| MD-T71 | P0 | N parallel reserves for the same `order_id` | one reservation, others replay 200; counters add once |
| MD-T72 | P0 | Property: random sequences of reserve/authorize/commit/release/mark-unknown from several workers | never negative, never above cap, `spent` never decreases, state machine never reaches an illegal state |
| MD-T73 | P0 | DB CHECK backstop: raw insert/update (superuser fixture) that would break `spent+reserved<=max` | rejected by constraint |
| MD-T74 | P0 | Commit twice; commit with other amount; release after commit; commit after release | idempotent / 409 `AMOUNT_MISMATCH` / 409 `INVALID_RESERVATION_STATE`; counters unchanged |
| MD-T75 | P0 | Commit creates grant atomically with counter move and two outbox rows; fault injected before COMMIT | all or nothing (C13-style crash) |
| MD-T76 | P0 | Reservation TTL: lazy release on touch and sweeper; `CAPTURING`/`CAPTURE_UNKNOWN` never released by TTL | verified with injected clock |
| MD-T77 | P0 | `authorize-capture` on expired reservation | 409 `RESERVATION_EXPIRED`, reservation released, checkout must re-reserve |
| MD-T78 | P0 | Lock timeout injection (hold the row lock in another session) | 503 `LOCK_TIMEOUT`; caller retry succeeds after release; no partial state |
| MD-T79 | P1 | Different mandates in parallel do not block each other (no global lock) | latency independent of other mandate's held lock |
| MD-T7A | P0 | Exhaustion: commit brings `spent == max` | state `exhausted`; further reserve `MANDATE_EXHAUSTED` |
| MD-T7B | P1 | Neon pooled endpoint: transaction-scoped `FOR UPDATE` holds under pooling (run MD-T70 against the hosted DB once) | pass or fallback decision recorded (I) |

### 2.8 Expiry and clock (spec sec 5)
| ID | P | Case | Expected |
|---|---|---|---|
| MD-T80 | P0 | Expiry computed at read time with no sweeper running | evaluate returns `MANDATE_EXPIRED` at/after `expires_at` |
| MD-T81 | P0 | `mandate.expired` emitted exactly once (lazy read + sweeper both run, concurrently) | one outbox row (deterministic event id) |
| MD-T82 | P1 | Clock jumps backward/forward (C18 on the mandate host clock) | a mandate that read as expired never reads active again in the same process run (monotonic guard in test clock); no duplicate events |
| MD-T83 | P1 | Authorize on a mandate expiring between reserve and authorize | 409 `MANDATE_EXPIRED`, released |

### 2.9 AuthN/Z, errors, hygiene
| ID | P | Case | Expected |
|---|---|---|---|
| MD-T90 | P0 | T10 IDOR matrix auto-enumerated from OpenAPI: buyer B vs buyer A on every mandate/grant/reservation path | 404 (or 403 for service-only paths) everywhere |
| MD-T91 | P0 | T19: missing, expired, wrong-aud, `alg=none`, forged signature, wrong issuer | 401 on all endpoints incl. `/internal/*` |
| MD-T92 | P0 | Role/service matrix: merchant cannot revoke or see `intent_text`; shopping-agent cannot reserve/commit/revoke; resolution cannot evaluate/reserve; checkout cannot revoke on behalf of a buyer | 403 |
| MD-T93 | P0 | T14 direct call to mandate without internal JWT (compose) and via gateway for unexposed routes (`evaluate`, reservations) | 401 / gateway 404 |
| MD-T94 | P0 | T21 negative fuzz (Schemathesis from OpenAPI) | no 500, no stack trace, no SQL or path in bodies |
| MD-T95 | P0 | T26 log redaction: sign, evaluate, tamper, errors with canary strings in `intent_text`, nonce, key | canaries absent from logs and events (events carry only `intent_text_hash`) |
| MD-T96 | P0 | T13: gitleaks on repo + env manifest test (no forbidden vars; `MANDATE_HMAC_KEY*` absent elsewhere) | green |
| MD-T97 | P1 | Rate limit and body size caps at gateway and app level | 429 / 413 |
| MD-T98 | P1 | Merchant minimal view contains no `buyer_id`, `intent_text`, spend figures | schema test |

### 2.10 Events and outbox (spec sec 11)
| ID | P | Case | Expected |
|---|---|---|---|
| MD-T9A | P0 | Event row exists iff the state change committed (rollback drops event) | atomic |
| MD-T9B | P0 | Payload scan: no `intent_text`, nonce secrets beyond audit spec, keys, HMAC; schema-valid | contract tests |
| MD-T9C | P0 | C16 audit down: sign and spend continue; backlog drains; audit chain verifies and contains `mandate.signed` (T24) | verified in compose |
| MD-T9D | P0 | C21 duplicate/redelivered events and storm replay | consumers dedupe by `event_id`; deterministic ids prevent producer duplicates |
| MD-T9E | P1 | C22 sleeping consumer: push fails, relay retries, `GET /internal/outbox?after=` catch-up | no loss |
| MD-T9F | P1 | Order of `mandate.signed` before `cart.checked` and `order.*` in audit chain for one scenario | ordered |

## 3. Test data and tooling
- Personas (seeded accounts; credentials from env, never in docs): `buyer_a`, `buyer_b` (IDOR attacker), mandate templates: tight (low cap, one merchant), wide, expiring-soon, expired, revoked, over-protection-terms (invalid on purpose).
- Fixtures via API (preview + sign), not SQL, so hashes/HMAC are real; superuser fixture only for tamper tests, isolated per test schema `t_mandate_<random>`; migrations applied per module; roles/grants recreated so grant bugs are caught (test-strategy L3).
- Injected clock for expiry/TTL/nonce tests (no sleeps). Test HMAC keys are generated per test session; none are real.
- Neighbor fakes generated from committed OpenAPI (checkout, audit sink, resolution sink); a hostile checkout fake that tries out-of-order calls (commit before authorize, capture after refused authorize).
- Coverage floors: mandate is a money-path service: >= 85% lines, >= 75% branch (OUR heuristic, I; test-strategy sec 10). Mutation testing on canonicalizer, evaluate, and ledger transitions is optional (I).
- Performance: record evaluate and reserve latency percentiles in S2 on Profile B and local A (test-strategy sec 12); no target pre-committed.

## 4. CI side-by-side
Two jobs run in parallel on every PR; both required to merge:
- `profile-b`: mandate mounted in the `core` host in-process (`PS_MANDATE_INPROCESS_TRANSPORT=true`), other `core` services real or faked.
- `profile-a`: `docker compose up` with mandate as its own container, HTTP between services, real internal JWT verification.
- The same suite (U, P, C, I tiers, MD-T cases, E5/E6) runs against both through a transport fixture; results are diffed and any test passing in one profile but failing in the other fails CI. This catches in-process shortcuts, missing audience checks, header/transport differences, cold-start timeouts.
- Extra B-only check: schema/role isolation still enforced in-process (cross-schema SELECT denied; `core` neighbors cannot import mandate repositories; direct-DB test from checkout role gets permission denied).
- Extra A-only check: T14 direct call without JWT.
- Hosted smoke after each deploy (not a PR gate): sign -> evaluate -> reserve -> release on a throwaway mandate, then `scripts/warmup`; one cold run after >= 12 h idle before the Oct 23 cut line and again before submission (sprint-plan).
- Nightly: full suite on A, MD-T7B against Neon, 24 h-idle cold run when scheduled. Flakes: quarantine policy per test-strategy sec 9 (concurrency tests are never allowed to be silenced; a flake in MD-T64/T70 is treated as a Sev1 candidate until explained).

## 5. Definition of done (service)
- [ ] Every P0 case above passes in CI on BOTH profiles; no skipped P0 (the only allowed `xfail(strict)` is the D1 (b) variant, MD-T68).
- [ ] 100% of the closed hard-block list has a failing-fixture test (MD-T50) and each mutation fixture in MD-T05 is detected.
- [ ] Concurrency suite (MD-T64, T70, T71, T72) green over repeated runs, including once on the hosted Neon DB (MD-T7B), zero invariant violations.
- [ ] Widening and replay fixtures (MD-T30..T47) 100% rejected.
- [ ] OpenAPI and event schemas committed; contract diff green; neighbors' contract tests (checkout, resolution, gateway, audit) green against the real mandate.
- [ ] Migration up/down tested; roles/grants/triggers verified on Neon with the real runtime role.
- [ ] Hosted: 5 consecutive clean sign -> cart -> reserve -> capture-authorize -> commit runs, one after >= 12 h idle; key rotation drill done once; `GET /verify` demo scripted and matches the audit chain.
- [ ] No secrets (gitleaks full history), env manifest test green, logs/events scan clean (T26, T13), honest-claims grep clean (T25).
- [ ] Docs state: demo-grade server HMAC, not buyer-held key, no non-repudiation; D1 is confirmed (revoke = future spend only, earned protection stands, per 00-platform-prd.md) — state this plainly in the README, not as a known-issue.
- [ ] Coverage floors met; evaluate/reserve latency recorded.
- [ ] Rollback rehearsed once (redeploy previous SHA + `/internal/sweep` + checkout reconcile).

## 6. Gate mapping (test-strategy sec 8)
| Sprint | Required green for mandate |
|---|---|
| S1 (to Oct 16) | lint/types; L1 mandate (MD-T01..T08, T20..T24, T30..T38, T40..T46, T50..T59, T60..T62, T90..T91, T95..T96); T4 hard-blocks; T19; gitleaks; compose boots |
| S2 (to Oct 23, cut line) | + ledger and race (MD-T63..T6B, T70..T7A), tamper/audit cross-check (MD-T09), events (MD-T9A..T9D), IDOR T10 (MD-T90), T16-style preview limits, spike of Neon pooling (MD-T7B first run), side-by-side CI required |
| S3 (to Oct 30) | + chaos subset on mandate PRs (C14, C16, C21, C22, C23), key rotation (MD-T11), grants read for resolution contract tests, T24 completeness with resolution events |
| S4 (to Nov 6 freeze) | all MD P0/P1, coverage floors, T21, T25, T26, hosted soak, no open Sev1/Sev2 |
Bug severity and ship rules: test-strategy sec 14. Any integrity, cap, or revoke-race failure is Sev1 (money/safety violation).
