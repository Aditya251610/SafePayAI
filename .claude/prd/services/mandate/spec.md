# mandate: spec

Date 2026-10-10. Labels: **V** verified, **VC** vendor/secondary claim, **I** inference/assumption. "(design)" = a decision made in this doc, not a fact about the outside world. Source of truth for requirements: `prd.md` (REQ-MD-xxx). On conflicts, `architecture/service-map.md` and `architecture/adr.md` win; deviations are listed in sec 12. No secret values appear here; names only. Illustrative amounts in examples are NOT product defaults.

## 1. Position
- Slug `mandate`, schema `mandate`, DB role `svc_mandate` (ADR-004), Python 3.12, FastAPI, Pydantic v2 (`extra=forbid`), SQLAlchemy 2 + Alembic (ADR-002).
- Profile B: mounted in the `core` process with checkout, catalog, tracking, resolution, audit; Profile A: own container. Same code, same router, same token-audience check (`aud=mandate`) in both (overview sec 8).
- Pure authority: no LLM, no PayPal credentials, no catalog dependency, no outbound sync calls (service-map). Outbound traffic = outbox push of its own events only (ADR-003).
- Two jobs: (1) the signed, immutable Mandate (terms + proof), (2) the server-side ledger that makes the cap real across concurrent orders (reservations, spent) plus the per-order protection grant that survives revoke (sec 8).

## 2. Mandate schema (exact fields)
### 2.1 Signed terms (immutable; DB trigger blocks UPDATE/DELETE; no UPDATE grant)
| Field | Type | Source | Rules |
|---|---|---|---|
| `mandate_id` | uuid v4 | server | generated at sign; also PayPal `custom_id` (V: survives onto capture) |
| `buyer_id` | text | internal token `sub`/`act` only | never in body; body field -> 422 `FIELD_NOT_ALLOWED` |
| `schema` | const `"mandate.v1"` | server | version registry; unknown version = integrity failure |
| `currency` | `"USD"` | body, must equal `PS_MANDATE_CURRENCY` | v1 single currency (I; multi-currency is a non-goal) |
| `max_total_minor` | int > 0 | body | integer minor units, includes fees; <= `PS_MANDATE_MAX_TOTAL_CEILING_MINOR`; JSON integer only, floats rejected |
| `max_qty_per_line` | int >= 1 | body optional, else `PS_MANDATE_DEFAULT_MAX_QTY_PER_LINE` | <= `PS_MANDATE_MAX_QTY_PER_LINE_CEILING`; materialized before hashing; source of hard block `QTY_CAP` |
| `merchant_allowlist` | list of `{merchant_id, display_name}` | body | 1..`PS_MANDATE_MAX_MERCHANTS` entries; unique `merchant_id`; sorted by `merchant_id`; `merchant_id` matches `^[a-z0-9][a-z0-9_-]{0,63}$`; `display_name` 1..64 chars, same text rules as `intent_text`. Only `merchant_id` is enforced; `display_name` is label text for the screen (sec 12 Q3) |
| `intent_text` | text | body | 1..`PS_MANDATE_INTENT_MAX_CHARS`; NFC; trimmed; no control, format, bidi, line-break chars (sec 3.4). UNTRUSTED when later given to an LLM (shopping-agent treats it as data) |
| `expires_at` | UTC timestamp | body | `Z`, second precision; between now+`PS_MANDATE_MIN_EXPIRY_SECONDS` and now+`PS_MANDATE_MAX_EXPIRY_SECONDS` at sign time |
| `protection` | object (sec 9) | body | `{kinds_covered[], max_refund_minor, deliver_by_days}` |
| `revoke_effect` | const `"FUTURE_ONLY"` | server (client may echo, must equal) | the buyer-visible D1(a) semantics are part of the signed terms (sec 8) |
| `policy_version` | text | server (client may echo, must equal `PS_MANDATE_POLICY_VERSION`) | pins the 3 hardcoded merchant policies for resolution; mismatch -> 409 `POLICY_VERSION_MISMATCH` |
| `nonce` | 128-bit random, base64url | server-issued at preview | single use (sec 10.1); stored as SHA-256 hash, raw value also inside `canonical_json` so the hash is reproducible (design: nonce is burnt after use, so retaining it is harmless) |
| `created_at` | UTC timestamp | server | `Z`, second precision |
| `render_version` | const `"render.v1"` | server | selects the plain-language template (sec 4) |
| `screen_text_hash` | sha256 hex | server (client echo must match) | hash of the exact rendered text (sec 4) |

### 2.2 Proof columns (immutable)
`canonical_json` (the exact signed bytes as text), `mandate_hash` (sha256 hex), `hmac` (hex), `hmac_alg` (`HMAC-SHA256`), `hmac_key_id`, `signed_at`. The raw HMAC is never returned by public APIs (only `hmac_valid` via `/verify`).

### 2.3 Mutable / derived (separate tables, never in the signed hash)
- `revocations(mandate_id UNIQUE, revoked_at, reason_code, actor_ref)`: INSERT-only; presence = revoked.
- `mandate_spend(mandate_id PK, max_total_minor [copy], spent_minor, reserved_minor, version, updated_at)` with `CHECK (spent_minor >= 0 AND reserved_minor >= 0 AND spent_minor + reserved_minor <= max_total_minor)`. This is the only row that is locked for spend decisions (sec 7). Created in the same transaction as the mandate. The `max_total_minor` copy is protected by trigger (cannot change).
- `spend_reservations` (sec 7.2) and `protection_grants` (sec 9.2).
- `nonces` (issued) and `nonce_uses` (consumed; INSERT-only, PK on nonce hash).
- `idempotency_keys(scope, key, request_hash, response, created_at) UNIQUE(scope, key)`.
- `outbox` (sec 11). `mandate_attestations` (only if REQ-027 is built; sec 10.4).
- Status is NOT stored: derived at read time (sec 5). Table list vs `data-architecture.md` differences are in sec 12 (C4).

### 2.4 Indexes (no cross-schema FKs; ADR-004)
`mandates(buyer_id, created_at DESC)`, `spend_reservations(mandate_id, state)`, `spend_reservations(order_id) UNIQUE per mandate`, `protection_grants(order_id) UNIQUE`, `protection_grants(capture_id) UNIQUE`, `protection_grants(mandate_id)`.

## 3. Canonical JSON, hash, HMAC (REQ-MD-003)
### 3.1 canon.v1 rules (JCS-style, RFC 8785 inspired; not claimed full RFC 8785 conformance, I)
- UTF-8, no whitespace, object keys sorted by code point (all keys ASCII in v1, so identical to JCS order), arrays keep their defined order (sets are pre-sorted: `merchant_allowlist` by `merchant_id`, `kinds_covered` ascending).
- Numbers: JSON integers only, |n| <= 2^53-1; floats, `Decimal`, NaN, Infinity, exponents rejected. Beware `bool` being an `int` subclass in Python: the serializer is custom (explicit type switch) and fails closed on any other type.
- Strings: NFC; reject unpaired surrogates; escaping = JSON minimum (`"`, `\`, control chars; non-ASCII emitted raw). Free text rejects control and format characters anyway (3.4).
- Timestamps: `YYYY-MM-DDTHH:MM:SSZ`, UTC only; offsets other than `Z` and fractional seconds rejected.
- No `null` in the hashed object. Optional inputs are materialized with their defaults before hashing, so the same effective terms always give the same bytes.
- Hashed object keys (v1): `canon, schema, render, mandate_id, buyer_id, currency, max_total_minor, max_qty_per_line, merchant_allowlist, intent_text, expires_at, protection{kinds_covered,max_refund_minor,deliver_by_days}, revoke_effect, policy_version, nonce, created_at, screen_text_hash`. Any new key or semantic change = new `schema`/`canon` version; old versions stay verifiable forever (version registry in code; never delete a verifier).

### 3.2 Hash and HMAC
- `mandate_hash = sha256_hex(canonical_bytes)`.
- `hmac = HMAC-SHA256(K[key_id], b"mw.mandate.v1" || 0x00 || mandate_hash_bytes || 0x00 || buyer_id || 0x00 || nonce)`. Same inputs as auth-gateway sec 4.1 plus a domain-separation prefix (sec 12 C11). Constant-time compare. `hmac_alg` is stored so the algorithm is a parameter, not a hardcoded assumption (post-quantum posture: abstraction only, no PQ claim).
- Key = a purpose-separated secret, used for nothing else (sec 10.3).

### 3.3 Integrity check (REQ-MD-007), run on every evaluate / reserve / authorize-capture / commit / terms / verify
1. Load row; dispatch verifier by `schema`+`canon` (unknown -> fail).
2. Rebuild canonical bytes from the typed columns; must equal stored `canonical_json` byte for byte; `sha256` must equal `mandate_hash`.
3. Look up key by `hmac_key_id` (unknown or verify-only-expired -> fail `KEY_UNKNOWN`); recompute HMAC; constant-time compare.
4. Also confirm `mandate_spend.max_total_minor == max_total_minor` and `buyer_id` columns agree.
Failure = hard block `MANDATE_INTEGRITY_FAILED` (evaluate) / 409 (reserve, authorize, commit) / `integrity:"FAILED"` on reads; emits `mandate.integrity_failed` once per mandate (deterministic event id) and logs without terms. Why steps 2 and 3 are both needed: editing a column breaks step 2; editing columns plus `canonical_json` plus `mandate_hash` consistently still breaks step 3 unless the attacker holds the key (sec 15 states that case plainly).

### 3.4 Free-text validation (REQ-MD-020)
Reject: Unicode categories Cc, Cf (covers bidi controls, zero-width, BOM), Cs, Co, Cn, Zl, Zp; any `\n`/`\r`/`\t`; leading/trailing whitespace is trimmed (the trimmed value is what is hashed and shown); length caps in code points after NFC; `extra=forbid`; reject any float anywhere. Rejection is 422 `VALIDATION_ERROR` with the field path (never echoing the offending text into logs).

## 4. Plain-language rendering (REQ-MD-004)
- `render.v1(terms) -> text` is a pure function of the normalized terms (no clock, no locale, no catalog). Money = integer arithmetic with a fixed exponent table (`USD` = 2 decimals), format `USD 12.34`; dates = `YYYY-MM-DD HH:MM UTC`.
- The text is composed only of fixed template sentences plus escaped insertions of: money, count, `display_name (merchant_id)`, `intent_text` in straight quotes, kinds in words, days. Template (illustrative wording; final copy is a UX task but any edit bumps `render_version`):
  1. `DEMO MANDATE - sandbox only, not a legal agreement.`
  2. `Your shopping agent may buy only from: <name> (<id>); ...`
  3. `All purchases under this mandate together may not exceed <USD x.xx>, including fees.`
  4. `No single item line may exceed <n> units.`
  5. `Purpose you stated: "<intent_text>"`
  6. `This mandate expires <date>. You can revoke it at any time. Revoking stops new purchases; refund protection already earned on completed purchases stays.`  (this sentence encodes D1(a); sec 8; needs user confirmation)
  7. `If an order covered by this mandate is <late|lost|late or lost> (not delivered within <n> days of purchase, on the demo clock), a refund of up to <USD x.xx> is pre-approved. The refund is merchant-funded via a PayPal sandbox refund.`
- `screen_text_hash = sha256_hex(NFC UTF-8 bytes of the text)`; it is inside the hashed mandate object, so the signed proof binds the text.
- Flow: `POST /mandates/preview` returns the server-rendered text, its hash and a nonce bound to the terms digest (sec 10.1). The UI must display exactly `screen_text`. `POST /mandates` carries the terms and the echoed `screen_text_hash`; the server re-normalizes, re-renders and compares; mismatch -> 422 `SCREEN_TEXT_MISMATCH` (also catches a client that rendered its own different text).
- Limit (state it plainly): the hash proves the server-rendered text matches the signed terms, not that the buyer's eyes saw it. No "buyer saw X" claim.
- Banned phrases are asserted absent from templates by a unit test (T25): "PayPal-backed", "verified by PayPal", "legally binding", "non-repudiable", "tamper-proof", "guaranteed", "insured".

## 5. State machine (REQ-MD-008)
States are derived, in this precedence: `revoked` > `expired` > `exhausted` > `active`.
| State | Derivation (read time, server clock UTC) |
|---|---|
| revoked | `revocations` row exists |
| expired | not revoked and `now >= expires_at` |
| exhausted | not revoked/expired and `spent_minor >= max_total_minor - PS_MANDATE_EXHAUST_DUST_MINOR` (default dust 0, so exact equality; the user-visible block for practical over-spend is `OVER_CAP`, sec 12 Q6) |
| active | otherwise |
Allowed transitions: active -> exhausted | revoked | expired; exhausted -> revoked | expired. No transition out of revoked or expired; no reactivation, no editing (new authority = new mandate). Reservations in flight do not make a mandate exhausted (only `spent_minor` does).
- Expiry is computed at read time, so correctness never depends on a sweeper. The sweeper (REQ-MD-023) only emits `mandate.expired` once (deterministic event id) and releases stale `RESERVED` spends.
- Revoke on an `expired`/`exhausted` mandate: exhausted -> writes the revocation (200); expired -> 200 no-op with `status:"expired"` and no event (sec 12 Q4).
- Read-time clock = the mandate host's UTC clock. The demo clock (owned by `tracking`) does not drive mandate expiry (sec 12 Q2).
- `INVALID` is a read verdict (integrity failed), never a persisted state.

## 6. Deterministic cart checks (REQ-MD-009, -010)
`evaluate(mandate_snapshot, cart) -> {decision, hard_blocks[], advisory_flags[]}` is a pure function: no writes, no clock other than the injected `now`, no network, no AI input (the request schema has no intent-fit field; `extra=forbid`).
### 6.1 Input (all supplied by checkout, a trusted service caller; mandate cannot verify truth of prices, only consistency)
`cart = {currency, lines:[{sku, qty, unit_minor, line_minor, merchant_id, sku_known, stated_unit_minor?}], total_minor}`. Optional legacy `committed_minor` (from checkout C10) is accepted and ignored; mandate uses its own `spent_minor + reserved_minor` (sec 12 C2). Malformed input (missing fields, floats, qty < 1, empty lines, duplicate SKU lines) -> 422, which callers must treat as BLOCK (fail closed).
### 6.2 Hard-block list (closed, enumerated; REQ-MD-010). Every code needs a failing-fixture test.
| Code | Condition |
|---|---|
| `MANDATE_INTEGRITY_FAILED` | sec 3.3 fails. Short-circuits: no other check is trusted, only this block is returned |
| `MANDATE_REVOKED` | state revoked |
| `MANDATE_EXPIRED` | state expired (`now >= expires_at`) |
| `MANDATE_EXHAUSTED` | state exhausted |
| `MERCHANT_NOT_ALLOWED` | any line `merchant_id` not in `merchant_allowlist`; details list offending ids |
| `OVER_CAP` | `total_minor > max_total_minor - spent_minor - reserved_minor` (snapshot; the authoritative check is the reserve under lock, sec 7) |
| `UNKNOWN_SKU` | any line `sku_known == false` |
| `QTY_CAP` | any line `qty > max_qty_per_line` |
| `CURRENCY_MISMATCH` | cart or any line currency != mandate currency |
| `PRICE_MISMATCH` | any line has `stated_unit_minor` and it != `unit_minor` (agent-stated price != DB price) |
| `CART_ARITHMETIC_MISMATCH` | `line_minor != qty*unit_minor` or `total_minor != sum(line_minor)` |
Order: fixed (the table order) so the response and tests are stable. All applicable blocks are collected except after integrity failure. `decision = ALLOW` iff `hard_blocks` is empty.
### 6.3 Advisory flags (REQ-MD-024; informational; never change `decision`)
`NEAR_CAP` (total >= `PS_MANDATE_ADVISORY_NEAR_CAP_PERCENT` of remaining), `EXPIRES_SOON` (< `PS_MANDATE_ADVISORY_EXPIRES_SOON_SECONDS` left), `MULTI_MERCHANT` (more than one merchant in cart). Flags live in a separate function and type; `decision` is computed only from `hard_blocks`. Property test: for any flag configuration, the decision is identical.
### 6.4 What ALLOW means
ALLOW is a snapshot, not a capability. Money can only move after a successful reserve (sec 7), and the capture gate is `authorize-capture` (sec 7.3). Callers must not cache ALLOW (`Cache-Control: no-store` on every response).
### 6.5 Interaction with the advisory AI check
The AI intent-fit verdict (shopping-agent via checkout) can only tighten and runs after these checks pass. It is not an input here and cannot clear any block (T4).

## 7. Spend accounting (`spent_minor` transaction semantics) (REQ-MD-012, -013)
### 7.1 Invariants
- `spent_minor + reserved_minor <= max_total_minor` always: enforced in code under the row lock and by the DB `CHECK` as backstop.
- `spent_minor` moves only on `commit` (money captured), never decreases (gross, monotonic; refunds do not restore budget: Q7).
- `reserved_minor` = sum of amounts of reservations in `RESERVED`, `CAPTURING`, `CAPTURE_UNKNOWN`.
- Every transition is idempotent; every counter change and its outbox event are in one transaction.
### 7.2 Reservation state machine (`spend_reservations`)
Columns: `reservation_id`, `mandate_id`, `order_id` (checkout order id), `amount_minor`, `currency`, `proposal_hash` (audit tie), `state`, `expires_at` (only meaningful for `RESERVED`), `authorized_at`, `captured_at`, `capture_id`, `release_reason`, timestamps. `UNIQUE(mandate_id, order_id)`.
| From | Operation | To | Counter effect | Notes |
|---|---|---|---|---|
| (none) | reserve | RESERVED | reserved += amount | runs full evaluate under lock; refusal = 409 `RESERVATION_REFUSED` + `hard_blocks` |
| RESERVED | authorize-capture | CAPTURING | none | POINT OF NO RETURN; refused (and reservation auto-RELEASED) if revoked/expired/exhausted-by-others/integrity-failed or TTL passed |
| CAPTURING | mark-unknown | CAPTURE_UNKNOWN | none | checkout could not tell if PayPal captured |
| CAPTURING, CAPTURE_UNKNOWN | commit | CAPTURED | reserved -= a; spent += a | needs `capture_id`, amount equals reserved amount; creates the protection grant (sec 9.2) in the same txn; allowed even if the mandate is now revoked/expired (sec 8) |
| RESERVED | release | RELEASED | reserved -= a | buyer cancelled / order failed before authorize |
| CAPTURING, CAPTURE_UNKNOWN | release with `capture_outcome="NOT_CAPTURED"` | RELEASED | reserved -= a | only after checkout reconciled with PayPal and proved no capture; otherwise 409 |
| RESERVED (stale) | TTL expiry | RELEASED | reserved -= a | lazy at next touch under lock, plus sweeper; never applies to CAPTURING/UNKNOWN |
| CAPTURED, RELEASED | any other op | same | none | replay returns current state (idempotent); contradicting op (e.g. release after commit) = 409 `INVALID_RESERVATION_STATE` |
Reserve idempotency: same `(mandate_id, order_id, amount_minor)` returns the existing reservation (200); same key different amount = 409 `RESERVATION_CONFLICT`.
### 7.3 Locking protocol (Postgres, transaction-scoped only)
1. `BEGIN` (READ COMMITTED).
2. `SET LOCAL lock_timeout = PS_MANDATE_LOCK_TIMEOUT_MS; SET LOCAL statement_timeout = PS_MANDATE_STATEMENT_TIMEOUT_MS`. Timeout -> 503 `LOCK_TIMEOUT` (retryable; callers must retry idempotently, never assume success).
3. `SELECT ... FROM mandate_spend WHERE mandate_id = :id FOR UPDATE` (one lock per mandate; no multi-row locking, so no deadlock cycle).
4. Only after the lock: read revocation, expiry, mandate row (integrity check), reservation row. Re-reading after the lock is what makes "stop wins" true: revoke takes the same lock (sec 8), so revoke and authorize are totally ordered.
5. Apply the transition, update counters, insert outbox row(s), `COMMIT`.
No session-level advisory locks (PgBouncer-style pooling on Neon pooled endpoint; I, verify on the real host). The same lock protects revoke, reserve, authorize, commit, release, sweeper.
### 7.4 Crash and ambiguity rules
- Crash before commit: transaction rolls back; counters and outbox unchanged.
- Caller times out and does not know the result: retry the same call with the same ids (idempotent) or `GET /reservations/{id}`.
- `CAPTURING`/`CAPTURE_UNKNOWN` older than a threshold is an operator signal (log + metric), never auto-released: money may have moved.
- Amount mismatch at commit (PayPal captured a different amount than reserved): 409 `AMOUNT_MISMATCH`, reservation stays as is for human reconcile (Q10). Do not silently adjust `spent_minor`.

## 8. Revoke vs in-flight order vs earned protection (REQ-MD-011, -014, -015)
**Decision D1 (platform PRD sec 12), recommendation (a), ~70% PM confidence: revoke stops only future spending. Protection already earned on captured orders stays. NEEDS USER CONFIRMATION before the product copy and the signed `revoke_effect` are treated as final.** Until confirmed, this spec implements (a) because it is the safer reading for the buyer-visible promise (the merchant was paid under those terms; (b) would make the refund promise unreliable).
### 8.1 Behavior by order stage at the moment revoke commits (v1 = FUTURE_ONLY)
| Stage when revoke commits | Result |
|---|---|
| No reservation yet (cart checked, not confirmed) | evaluate/reserve now return `MANDATE_REVOKED`; checkout blocks the cart |
| `RESERVED` (PayPal order may exist, not approved or approved but not authorized) | revoke releases the reservation in the same transaction; a later `authorize-capture` returns 409 `MANDATE_REVOKED`; checkout must not capture (CANCELLED_REVOKED; PayPal order left to expire, no void API verified: checkout C11) |
| `CAPTURING` / `CAPTURE_UNKNOWN` (authorize won the lock first) | NOT stopped: money may already be captured. Commit stays allowed; the grant is created. This is not a bypass: authorize was the last point where stop could win |
| `CAPTURED` (grant exists) | grant unchanged; protection stays in force; resolution may open cases and offer refunds inside the grant terms |
- Race rule: revoke and authorize both take the mandate row lock; whichever acquires it first defines history. If authorize first, capture proceeds and revoke is recorded after; if revoke first, authorize is refused. A test asserts the ordering by DB timestamps over repeated runs (T23, C23).
- What revoke does NOT do: it does not reverse completed captures or refunds; it does not cancel a PayPal order that already exists; it does not touch grants; it does not stop approval links or offers that resolution issues under an existing grant (resolution owns those; conflict C12).
- Mandate expiry behaves the same way as revoke for new spending; grants have their own windows (sec 9.3) and outlive the mandate.
### 8.2 If the user chooses (b) or (c)
- (b) "revoke also cancels protection on open orders": new `revoke_effect` value + `render.v2` sentence; grants gain a `SUSPENDED` state flipped by revoke in the same transaction; resolution must check `protection_in_force`. Existing v1 mandates keep v1 semantics because the term is signed.
- (c) "buyer chooses at revoke time": revoke request carries `protection_choice`; stored on the revocation row; sentence changes again. Both are additive, small, and gated by the `revoke_effect` field; nothing else in this spec changes. This is why the decision is cheap to flip late but must be settled before the copy freeze (sprint-plan: copy freeze Nov 5).
- Events carry `revoke_effect` so audit shows which semantics applied.

## 9. Protection terms and grants (REQ-MD-015, -016)
### 9.1 Terms (inside the signed mandate)
`protection = {kinds_covered: subset of ["LATE","LOST"] (sorted, non-empty), max_refund_minor: int, deliver_by_days: int}`.
- Validation at signing: `0 < max_refund_minor <= max_total_minor` and `<= PS_MANDATE_REFUND_CAP_CEILING_MINOR`; `PS_MANDATE_DELIVER_BY_DAYS_MIN <= deliver_by_days <= PS_MANDATE_DELIVER_BY_DAYS_MAX`. Out of bounds -> 422 `TERMS_OUT_OF_BOUNDS` with `details.field`. Demo values for bounds are a user call (platform PRD D7), labelled illustrative.
- Meaning (matches resolution decision rows D8/D9): an order is protected until `captured_at + deliver_by_days` on the demo clock (checkout computes the date from `protection_window_days`; mandate does not read a clock for it). A refund request of kind in `kinds_covered`, amount <= `max_refund_minor`, inside the window is INSIDE_TERMS; anything else is OUTSIDE_TERMS and needs fresh buyer approval or human review. Amount derivation (full-order up to cap) is resolution's rule; mandate only publishes the cap.
- Wording constraint (D3): terms say "this shop's demo policy allows automatic refunds up to the cap shown. Sandbox illustration only." Never imply a merchant legally agreed.
### 9.2 Grant snapshot (created in the `commit` transaction)
`protection_grants`: `grant_id`, `mandate_id`, `order_id` UNIQUE, `capture_id` UNIQUE, `buyer_id`, `mandate_hash`, `terms` (jsonb copy: `kinds_covered, max_refund_minor, deliver_by_days, currency, revoke_effect, policy_version`), `terms_hash` (sha256 over canon.v1 of `{mandate_id, mandate_hash, terms}`), `captured_amount_minor`, `captured_at`, `grant_hmac` + `hmac_key_id` (same HMAC construction, different domain prefix `mw.grant.v1`), `created_at`. Immutable (trigger + no UPDATE grant). The snapshot makes protection independent of later mandate state and gives resolution a stable `terms_hash` for its check #3 (resolution sec 6).
### 9.3 Reads for resolution/checkout
`GET /grants?order_id=` and `GET /mandates/{id}/terms` return terms, `terms_hash`, `integrity` (grant HMAC and mandate HMAC re-verified now), `mandate_status`, `protection_in_force` (v1: true for any grant with `integrity=OK`). Available for revoked and expired mandates.

## 10. Nonce, replay, idempotency, keys
### 10.1 Nonce and replay (REQ-MD-005)
- Issue: `POST /mandates/preview` generates a 128-bit nonce (CSPRNG), stores `nonces(nonce_hash, buyer_id, purpose='mandate_sign', terms_digest, issued_at, expires_at)`; returns the raw nonce once. TTL `PS_MANDATE_NONCE_TTL_SECONDS` (auth-gateway starting value 120 s, I). `terms_digest = sha256(canon.v1(normalized terms))` so a nonce is valid only for the exact terms previewed (blocks widening between preview and sign).
- Consume (atomic, in the same transaction as the mandate insert): `INSERT INTO nonce_uses(nonce_hash, mandate_id, used_at)` after verifying a `nonces` row matching `(nonce_hash, buyer_id, purpose, terms_digest)` that is unexpired. `nonce_uses` PK violation = replay. INSERT-only avoids needing UPDATE on `nonces` (data-architecture grant model).
- Any failure (unknown, expired, used, wrong buyer, digest mismatch) -> 409 `NONCE_INVALID` with one generic message (no oracle); the internal reason code is logged.
- Replaying a captured signed request body: the nonce is burnt, so 409; replaying under another buyer: nonce bound to `buyer_id`, so 409.
- The nonce is also in the signed object, so a copied mandate row cannot be re-presented as a fresh signing.
### 10.2 Idempotency (REQ-MD-006)
`Idempotency-Key` required on `POST /mandates` (scope = `(buyer_id, "POST /mandates")`) and on `revoke`. Lookup happens BEFORE the nonce check so a safe client retry returns the original 201 body with `Idempotent-Replay: true`. Same key + same canonical request hash = original; same key + different hash = 409 `IDEMPOTENCY_KEY_REUSED` (checkout uses 422 for the same code: C6). Key row is written in the same transaction as the mandate. Retention `PS_MANDATE_IDEMPOTENCY_TTL_SECONDS`. Service-to-service reservation calls are idempotent by natural key `(mandate_id, order_id)` and by reservation state, not by header.
### 10.3 Key handling and rotation (REQ-MD-021)
- Secret names: `MANDATE_HMAC_KEY` (current) and `MANDATE_HMAC_KEY_PREVIOUS` (verify-only); ids in `PS_MANDATE_HMAC_KEY_ID` / `PS_MANDATE_HMAC_KEY_ID_PREVIOUS`. The secret keeps its purpose name — a settled, documented exception to the `PS_<SLUG>_*` convention, same category as `PAYPAL_CLIENT_ID`/`PAYPAL_CLIENT_SECRET` (see C5).
- Requirements: >= 256-bit random from a CSPRNG, generated outside the repo, set only in the platform dashboard of the process that mounts mandate. Boot validates presence, length and that the two ids differ; failure -> process refuses to sign and `/readyz` is not ready (fail closed). Key bytes never appear in logs, events, errors, health output or the DB. Separate from `PS_APIGATEWAY_SESSION_COOKIE_KEY`, `PS_APIGATEWAY_CSRF_KEY`, `APPROVAL_KEY`, ticket keys, JWT signing keys (auth-gateway sec 8).
- Rotation: (1) generate new key + id; (2) set current -> previous, new -> current, deploy; (3) new mandates/grants sign with new id; (4) old rows verify through `previous`; (5) drop `previous` only after `scripts/mandate-keys-in-use` reports zero live mandates (not expired/revoked) and zero grants with that id. Grants live longer than mandates, so rotate with this check. One rotation drill before submission (auth-gateway sec 3.4 plans the same).
- Suspected compromise: remove the key; every row signed with it fails verification (fail closed: `KEY_UNKNOWN`) until re-attested (10.4) or the demo is reset with fresh mandates. Forgery by an attacker holding the key is not preventable by this design; detection path = compare `mandate_hash` with the hash recorded in the audit chain at signing time (independent of the key).
### 10.4 Re-attestation after key compromise (REQ-MD-027, could)
Operator script (not a public endpoint): for each affected mandate/grant, recompute canonical bytes and `mandate_hash`, require equality with the `mandate_hash` recorded in the audit chain event `mandate.signed`; if equal, append a `mandate_attestations(mandate_id, key_id, hmac, attested_at, reason)` row signed with the new key; verification then accepts the newest attestation. If not equal, the mandate is quarantined (treated as integrity-failed) and the incident goes to the human. Only built if time allows; otherwise the runbook says "reset demo mandates".

## 11. Events (outbox, ADR-003; REQ-MD-017)
Envelope (data-architecture): `event_id, type, version, aggregate_id (mandate_id), payload, trace_id, created_at`. Row inserted in the same transaction as the state change; relay pushes HTTP to subscribers with retry; at-least-once, consumers dedupe by `event_id`. `event_id` for lifecycle events is deterministic (`uuid5(mandate_id, type[, extra])`) so a retried transaction cannot create duplicates. Payloads never contain `intent_text` (only `intent_text_hash`), raw nonce secrets beyond what audit spec lists, keys, or HMAC values.
| Event | Producer trigger | Consumers | Payload (summary) | Status |
|---|---|---|---|---|
| `mandate.signed` | successful sign | audit | `mandate_id, buyer_id, mandate_hash, screen_text_hash, render_version, policy_version, nonce, max_total_minor, currency, merchant_ids[], expires_at, protection, revoke_effect, hmac_key_id, intent_text_hash` | service-map; matches audit spec fields |
| `mandate.revoked` | first revocation commit | audit, checkout, resolution | `mandate_id, mandate_hash, revoked_at, reason_code, revoke_effect, released_reservations` | service-map |
| `mandate.expired` | sweeper or first read after expiry (once) | audit | `mandate_id, mandate_hash, expired_at` | service-map |
| `mandate.spend_committed` | commit | audit | `mandate_id, order_id, reservation_id, capture_id, amount_minor, spent_minor_after, remaining_minor_after` | proposed additive |
| `mandate.protection_granted` | commit (same txn) | audit, resolution | `grant_id, mandate_id, order_id, capture_id, terms_hash, mandate_hash` | proposed additive |
| `mandate.integrity_failed` | first detection | audit | `mandate_id, check` (which step failed), `key_id` | proposed additive |
Reservation create/release/authorize are not published as events (state is in the DB and queryable; keeps audit volume down, I). Audit remaining down never blocks signing or spending (service-map: audit is not on the money path); events queue in the outbox.

## 12. Conflicts and open questions
### 12.1 Conflicts found (service-map and ADR win; resolution chosen here)
| # | Conflict | Resolution in this doc |
|---|---|---|
| C1 | service-map lists 5 endpoints; this service needs `preview`, `summary`, list, `verify`, reservations, grants | Added as additive endpoints (api.md). Gateway, checkout, resolution owners must accept them |
| C2 | Checkout sends `committed_minor` to evaluate (checkout C10); service-map says evaluate is pure | Mandate owns `spent_minor/reserved_minor`; `committed_minor` accepted and ignored. Checkout should call reserve at confirm and authorize-capture before capture (its docs do not yet) |
| C3 | Nonce issuer: auth-gateway 4.1 says gateway; service-map and api-gateway C4 say mandate | Mandate issues and consumes (preview). Gateway adds a route for preview and keeps CSRF tokens |
| C4 | data-architecture table list: `mandates, revocations, nonces, protection_terms(auto_refund_cap_minor, deliver_by_day), idempotency_keys, outbox`, INSERT/SELECT only on nonces | Added `mandate_spend, spend_reservations, protection_grants, nonce_uses, (mandate_attestations)`; protection terms live inside the signed row plus the grant snapshot instead of a separate mutable table; field names follow resolution (`max_refund_minor`, `kinds_covered`, `deliver_by_days`); consumption via INSERT-only `nonce_uses`. UPDATE grants only on `mandate_spend, spend_reservations, outbox, idempotency_keys` |
| C5 | Env names: user asked `PS_MANDATE_*`; auth-gateway and other services' manifests forbid `MANDATE_HMAC_KEY` | **RESOLVED (settled exception, 2026-10-11)**: `MANDATE_HMAC_KEY`[`_PREVIOUS`] stays unprefixed, same category as the `PAYPAL_CLIENT_ID`/`PAYPAL_CLIENT_SECRET` exception — multiple services' CI env-manifest tests already hard-forbid the bare name, so renaming now would require a coordinated multi-service change for no functional benefit. All other mandate config is `PS_MANDATE_*`. |
| C6 | Idempotency key reuse: data-architecture and PRD say 409; checkout api.md uses 422 `IDEMPOTENCY_KEY_REUSED` | 409 here; checkout owner to align or map |
| C7 | JWT verification: ADR-006 says cached JWKS, auth-gateway 3.1 says static `trusted_issuers`, checkout uses `PS_CHECKOUT_INTERNAL_JWKS_URL` | Support both: `PS_MANDATE_TRUSTED_ISSUERS` (preferred, no cold-start network dependency) else `PS_MANDATE_INTERNAL_JWKS_URL` |
| C8 | Reason-code vocabulary in checkout lacks `MANDATE_INTEGRITY_FAILED`, `MANDATE_EXHAUSTED`, `CART_ARITHMETIC_MISMATCH`; audit event catalog has only 3 mandate events | Additive codes/events; checkout must pass unknown codes through as BLOCK; audit must accept new types |
| C9 | test-strategy C18 says expiry decisions use the tracking clock; mandate has no tracking dependency | Mandate uses real UTC; see Q2 |
| C10 | checkout sprint-tasks use freeze Nov 3 (I) | Follow sprint-plan: freeze Nov 6 |
| C11 | auth-gateway HMAC input has no domain prefix | Prefix added; inputs otherwise identical |
| C12 | auth-gateway sec 6: revoke cancels "pending approval tokens, unsent offers"; resolution C6 keeps snapshot protection | Under D1(a) grants and offers inside grants survive revoke; resolution must not cancel them on `mandate.revoked`. Needs resolution owner and user confirmation with D1 |
| C13 | Adapter authorization ticket (agent-and-mcp) does not mention mandate reservations | Recommend (I) checkout puts `reservation_id` in the ticket and only mints it after authorize-capture succeeded; adapter does not call mandate |
### 12.2 Open questions
- Q1 (D1) Confirm (a). Needed before copy freeze Nov 5 and before treating `revoke_effect=FUTURE_ONLY` as final. Owner: user.
- Q2 Should mandate expiry follow the demo clock so a judge can see "expired" on stage? Default no (real clock); the demo shows expiry by signing a short-lived mandate (min expiry config) or via a test fixture. A clock-offset hook would make the safety-critical clock mutable (rejected for v1).
- Q3 Merchant `display_name` is client-supplied label text; should mandate validate merchant ids against catalog at preview (adds a dependency) or accept as is? Default: accept, render both name and id.
- Q4 Revoking an already expired mandate: no-op 200 vs 409. Default no-op.
- Q5 Default and ceiling for `max_qty_per_line`: values are config; user picks demo values.
- Q6 Exhausted dust threshold (default exact equality). Is a "remaining below cheapest item" notion wanted? Needs catalog; default no.
- Q7 Do refunds restore budget? Default NO (gross spent monotonic; simpler, safer). Alternative: net spent after completed refunds, requires a refund event subscription.
- Q8 Fees: `total_minor` includes fees only if checkout supplies them (checkout C13); mandate treats `total_minor` as authoritative gross.
- Q9 Demo values for deliver-by bounds, refund cap ceiling, expiry bounds, nonce TTL (platform PRD D7). Unknown; config.
- Q10 Amount mismatch at commit: stay reserved and escalate (default) vs adopt the captured amount.
- Q11 Reservation TTL must exceed PayPal buyer approval time; PayPal order approval expiry is unknown (I). Set `PS_MANDATE_RESERVATION_TTL_SECONDS` after the S1 spike; an expired reservation just forces a re-reserve.
- Q12 Merchant read scoping: shared merchant login can read any mandate summary by id (UUID unguessable, minimal fields). Accept (I).

## 13. Config / env names (values only in platform env; none here)
| Name | Kind | Purpose |
|---|---|---|
| `PS_MANDATE_DATABASE_URL`, `PS_MANDATE_DB_POOL_SIZE` | config | pooled Neon URL, small pool |
| `PS_MANDATE_MIGRATION_DATABASE_URL` | secret | direct URL for the migration role; CI/deploy only, never in the runtime process |
| `MANDATE_HMAC_KEY`, `MANDATE_HMAC_KEY_PREVIOUS` | secret | sec 10.3 |
| `PS_MANDATE_HMAC_KEY_ID`, `PS_MANDATE_HMAC_KEY_ID_PREVIOUS` | config | key ids |
| `PS_MANDATE_INTERNAL_JWT_AUDIENCE` (= `mandate`), `PS_MANDATE_TRUSTED_ISSUERS`, `PS_MANDATE_INTERNAL_JWKS_URL` | config | token verification (C7) |
| `PS_MANDATE_POLICY_VERSION`, `PS_MANDATE_CURRENCY` | config | pin and currency |
| `PS_MANDATE_MAX_TOTAL_CEILING_MINOR`, `PS_MANDATE_DEFAULT_MAX_QTY_PER_LINE`, `PS_MANDATE_MAX_QTY_PER_LINE_CEILING`, `PS_MANDATE_MAX_MERCHANTS`, `PS_MANDATE_INTENT_MAX_CHARS` | config | term bounds |
| `PS_MANDATE_MIN_EXPIRY_SECONDS`, `PS_MANDATE_MAX_EXPIRY_SECONDS` | config | expiry bounds at signing |
| `PS_MANDATE_REFUND_CAP_CEILING_MINOR`, `PS_MANDATE_DELIVER_BY_DAYS_MIN`, `PS_MANDATE_DELIVER_BY_DAYS_MAX` | config | protection bounds |
| `PS_MANDATE_NONCE_TTL_SECONDS`, `PS_MANDATE_IDEMPOTENCY_TTL_SECONDS` | config | replay windows |
| `PS_MANDATE_RESERVATION_TTL_SECONDS`, `PS_MANDATE_STUCK_CAPTURE_ALERT_SECONDS`, `PS_MANDATE_EXHAUST_DUST_MINOR` | config | spend ledger |
| `PS_MANDATE_LOCK_TIMEOUT_MS`, `PS_MANDATE_STATEMENT_TIMEOUT_MS` | config | lock behavior |
| `PS_MANDATE_ADVISORY_NEAR_CAP_PERCENT`, `PS_MANDATE_ADVISORY_EXPIRES_SOON_SECONDS` | config | advisory flags |
| `PS_MANDATE_SIGNING_ENABLED` | config | false -> `POST /mandates` returns 503 `SIGNING_DISABLED` (kill switch; reads, evaluate and revoke keep working) |
| `PS_MANDATE_AUDIT_BASE_URL`, `PS_MANDATE_CHECKOUT_BASE_URL`, `PS_MANDATE_RESOLUTION_BASE_URL`, `PS_MANDATE_INPROCESS_TRANSPORT`, `PS_MANDATE_OUTBOX_FLUSH_INTERVAL_SECONDS` | config | event relay targets and transport |
| `INTERNAL_TICK_SECRET` | secret (shared name) | guards `/internal/*` cron endpoints |
| `PS_MANDATE_LOG_LEVEL` | config | logging |
CI env-manifest test: mandate's manifest must NOT contain `PAYPAL_*`, `LLM_*`, `APPROVAL_KEY`, `PS_CHECKOUT_TICKET_HMAC_KEY`, session/CSRF keys; no other service's manifest may contain `MANDATE_HMAC_KEY*`.

## 14. Error model (REQ-MD-019)
Body: `{"error":{"code":"STABLE_CODE","message":"human text","details":{}},"request_id":"..."}`. No stack traces, no SQL, no internal paths (T21). Stable codes and statuses are listed in `api.md` sec 3. Principles: wrong owner = 404 `MANDATE_NOT_FOUND` (not 403, no existence oracle); a BLOCK from `evaluate` is a normal 200 result, not an error; business refusals on ledger calls are 409 with a machine code; unknown input is 422 and callers fail closed; dependency/lock/DB trouble is 503 and callers retry only idempotently.

## 15. Honest-claims constraints
May say: "server-enforced, deterministic mandate checks"; "terms are immutable and hash-and-HMAC protected (demo-grade, server-held key)"; "the signed hash covers the exact text shown"; "revoke stops future purchases; earned protection stays (pending confirmation)"; "tamper-evident: a changed stored mandate fails verification".
Must NOT say: signed by the buyer's key; non-repudiable; legally binding; PayPal-backed/verified/protected; tamper-proof; compliant; fraud-proof; "the buyer saw X"; real money; merchant legally agreed. A holder of `MANDATE_HMAC_KEY` or DB owner access can forge a mandate; the audit chain copy of `mandate_hash` is the independent check. Refund is "merchant-funded via PayPal refund"; protection window is a demo window, not PayPal's. All screens with mandate data carry the sandbox/demo banner.

## 16. Observability and logging
JSON logs with `trace_id`, `request_id`, `mandate_id`, `reservation_id`, outcome code; never `intent_text`, nonce, HMAC, keys, tokens, or full terms (T26). Metrics (logged counters, no paid APM): sign ok/fail by code, evaluate decisions by block code, reserve refusals, lock timeouts, integrity failures, reservations stuck in `CAPTURING`/`CAPTURE_UNKNOWN`, outbox backlog. Evaluate latency is measured in S2 and recorded; no target pre-committed (I).
