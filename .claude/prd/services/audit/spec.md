# audit - technical spec

Labels: V verified, VC vendor claim, I inference/unverified. Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 core (no ORM magic on the hot path) + Alembic, psycopg 3 (ADR-002). No code here: tables as pseudo-SQL, behavior in prose.

## 1. Position in the system
- Slug `audit`; schema `audit` in the shared Neon Postgres (ADR-004). Runs inside `core` in Profile B (in-process with mandate, checkout, ...) but keeps its own DB role, router and token-audience check (overview section 8). Profile A: own process.
- Inbound: producers push events (HTTP, service JWT, `aud=audit`). Outbound: none. Reads: gateway for the web grid.
- Not on the money path. Producers never wait on audit (outbox, ADR-003).

## 2. Data model (pseudo-SQL, schema `audit`)

### 2.1 `audit.entries` (the chain)
```
seq            BIGINT      PRIMARY KEY            -- gapless, assigned by writer (not a sequence)
chain_id       TEXT        NOT NULL               -- constant per environment, e.g. 'ps-demo-1'
event_id       UUID        NOT NULL UNIQUE        -- producer-generated; idempotency key
event_type     TEXT        NOT NULL               -- catalog name, e.g. 'REFUND_COMPLETED'
event_version  INT         NOT NULL
producer       TEXT        NOT NULL               -- service slug, must equal verified token sub
occurred_at    TIMESTAMPTZ NOT NULL               -- producer clock (untrusted)
recorded_at    TIMESTAMPTZ NOT NULL               -- audit clock (inside the hashed content)
actor_type     TEXT        NOT NULL               -- buyer|merchant_shared|reviewer_selfasserted|service|system|paypal_hint
actor_id       TEXT        NOT NULL
auth_method    TEXT        NOT NULL               -- session+csrf|session+csrf+nonce|session+approval_token|service_jwt|hmac|paypal_return_state|none
request_id     TEXT        NOT NULL
trace_id       TEXT        NOT NULL
-- subject refs: denormalized from content for grid filters and role scoping (also inside the hash)
buyer_id       TEXT        NULL
mandate_id     TEXT        NULL
order_id       TEXT        NULL
case_id        TEXT        NULL
canonical      TEXT        NOT NULL               -- EXACT bytes (UTF-8) that were hashed
payload        JSONB       NOT NULL               -- parse(canonical).payload, for querying only
prev_hash      CHAR(64)    NOT NULL UNIQUE        -- hex SHA-256; genesis uses 64 zeros
row_hash       CHAR(64)    NOT NULL UNIQUE
```
- `UNIQUE(prev_hash)` is a structural fork guard: two rows cannot share a parent even if locking were bypassed.
- `canonical` is the source of truth for hashing; `payload` and the subject-ref columns are derived copies. Verify checks derived == parsed canonical (catches an edit to a copy column).
- Row 1 (genesis, event_type `CHAIN_GENESIS`) is inserted by the migration as owner. Its `row_hash` is the first anchor.

### 2.2 `audit.verify_runs` (INSERT/SELECT, informational, NOT hashed)
`id, started_at, finished_at, head_seq_at_start, ok BOOL, first_bad_seq NULL, reason NULL, requested_by_actor_id, request_id`. Lets the grid show "last verified". Editing it proves nothing (stated in UI).

### 2.3 `audit.head_exports` (INSERT/SELECT, informational)
`id, exported_at, seq, row_hash, signature NULL, requested_by_actor_id`. History of anchors handed out, not trusted by verify.

### 2.4 No other tables
No outbox (audit emits no events), no inbox (idempotency is the `event_id` unique key).

## 3. Chain concurrency design

### Options
| option | how | pros | cons |
|---|---|---|---|
| A. Single writer process | one in-process queue and one asyncio lock | no DB lock | breaks on Render deploy overlap (two instances briefly), on Profile A scale-out, and on restart races; a bug forks silently |
| B. Advisory lock per append (CHOSEN) | `pg_advisory_xact_lock(<const>)` at start of the append txn, read head, insert | correct with any number of instances; lock released automatically at commit/rollback; works through a transaction-mode pooler (xact-level locks only, not session-level; VC from PgBouncer docs, verify in test T-AU-12) | writers serialize (acceptable, see throughput) |
| C. Serializable txn + retry | rely on SSI conflicts | no explicit lock | retry storms on contention, more complex |
| D. Per-aggregate chains | many small chains | parallel | brief requires one GLOBAL chain; more anchors to manage |

### Chosen algorithm (append of a batch of 1..N events)
1. Validate envelope and payload (schema per type), verify caller (service JWT, `sub` == `producer`), check actor allowlist (section 5). Canonicalize each event OUTSIDE the lock (CPU work off the critical section) except `recorded_at`, `seq`, `prev_hash` which need the head: recorded_at is taken inside the txn; canonical text is built after the head is known because content includes `recorded_at` but NOT `seq`/`prev_hash` (so canonicalization of event content can be done outside; only `recorded_at` is stamped inside, cheap).
2. `BEGIN`; `SELECT pg_advisory_xact_lock(<audit_chain_lock_key>)`.
3. Duplicate check: `SELECT seq FROM entries WHERE event_id = ANY(:ids)`. Duplicates are returned as `duplicate` (not inserted).
4. `SELECT seq, row_hash FROM entries ORDER BY seq DESC LIMIT 1` (index-only via PK). Empty = configuration error (genesis missing), refuse.
5. For each new event in order: `seq = head.seq+1`, `prev_hash = head.row_hash`, `row_hash = SHA256(DOMAIN || prev_hash || canonical)` (section 4); INSERT; advance head.
6. A BEFORE INSERT trigger on `entries` independently takes the same advisory lock (re-entrant in the same txn), checks `NEW.seq = max(seq)+1` and `NEW.prev_hash = row_hash of max(seq)`; otherwise raises. The trigger is the guard against a buggy or second writer; it does not compute the hash (hash logic stays in tested Python).
7. `COMMIT`. On unique-violation or trigger error: roll back, retry the whole append up to a small bounded count (value I, config), then 503 so the producer's outbox retries.

### Why not move everything to the trigger
Hash computation in plpgsql would duplicate canonicalization in two languages and make golden-vector testing harder. Python computes; DB verifies linkage.

### Throughput on a free Postgres
- No measured number exists yet (unknown). Reasoning (I): each append txn is a few round trips (lock, head select, insert, commit); on Neon the dominant cost is network RTT to the (possibly cold) compute plus the 5-minute scale-to-zero resume (resume latency I, commonly cited ~1-2 s VC). Lock hold time is one txn; writers serialize.
- Expected demo volume is hundreds of events, not thousands (overview, I). Even a pessimistic serialized rate is not the constraint; cold start is.
- Levers if needed: batch append (`POST /internal/events/batch`: one lock, one commit for N rows); relay coalesces by producer; keep txn minimal (no verify inside).
- Test-plan T-AU-13 measures append p50/p95 and batch effect on Neon free and records them in the test report; no target is promised before then.
- Neon CU-hours are a cap (100 CU-h/project/month, V per deployment doc): audit never pings the DB on a timer (health is DB-free); verify runs on demand or on a cron limited to review windows.

### Connection use
- Use the POOLED Neon endpoint for the app role (deployment doc). Pool size small (config `PS_AUDIT_DB_POOL_MAX`); statement cache/prepared statements OFF (`prepare_threshold=None` in psycopg) because transaction-mode poolers do not retain prepared statements (VC). Connection limit of the free plan is unknown (I); verify at S1.
- Migrations use the DIRECT endpoint with the owner role, from CI/local only.

## 4. Canonical content serialization (v1)

Goal: byte-identical output for equal logical content in writer, verifier, and any third-party re-implementation.

- Content object (what is hashed, exactly these keys):
```
{ "v": 1, "chain_id", "event_id", "event_type", "event_version", "producer",
  "occurred_at", "recorded_at",
  "actor": {"type","id","auth_method","session_id_hash"?},
  "request_id", "trace_id",
  "refs": {"buyer_id"?,"mandate_id"?,"order_id"?,"case_id"?},
  "payload": { ... per-type fields ... } }
```
- Encoding: RFC 8785 (JSON Canonicalization Scheme) rules: UTF-8, object keys sorted by UTF-16 code unit, no whitespace, minimal string escapes, absent optional keys omitted (never `null` placeholders).
- Numbers: payloads may contain only integers (money in integer minor units, brief) and strings/booleans/arrays/objects. FLOATS FORBIDDEN (schema rejects them), which removes the number-formatting risk in JCS.
- Strings: Unicode NFC normalized before canonicalization; no lone surrogates (rejected).
- Timestamps: UTC, format `YYYY-MM-DDTHH:MM:SS.ffffffZ` (exactly 6 fractional digits). Stored `TIMESTAMPTZ` is for querying only; the text in `canonical` is authoritative.
- Hashes in payload: lowercase hex SHA-256 strings.
- Row hash: `row_hash = hex(SHA256( b"safepayai.audit.v1\n" + prev_hash_hex_ascii + b"\n" + canonical_utf8 ))`. Domain prefix prevents cross-use of hashes; version `v` allows later change (verifier dispatches on `v`).
- Genesis: `prev_hash = "0"*64`; payload `{ "note": "genesis", "created_by": "migration" }`.
- Golden test vectors committed under `services/audit/tests/vectors/` (inputs, expected canonical bytes, expected hashes). A separate dependency-free Python script `scripts/verify_chain_standalone.py` (stdlib only: json export + hashlib) lets a third party verify an exported chain without our service.
- Keyed vs plain hash: plain SHA-256 so third parties can verify. Trade-off: anyone with DB write can recompute the chain. Mitigated only by anchors/signed heads (section 11), not by the hash.

## 5. Actor stamping

Rule (auth-gateway section 7): only verified tokens produce trustworthy actor fields; callers cannot self-assert.

Mechanism:
1. At the moment of the state change, the PRODUCER reads the actor from the VERIFIED inbound internal token (`act` claim: actor_type, actor_id, auth_method, role) and the `req` claim (request_id). It writes them into the outbox row with the state change. Producers have no API to choose arbitrary values.
2. For system-originated work (poller, reconcile, AI call logs) the actor is `system`/`service` with `actor_id` = service id.
3. The relay pushes the event with a fresh service JWT (`sub=<producer>`, `aud=audit`, scope `svc:audit`).
4. Audit verifies: (a) token signature, aud, exp, kid, iss allowlist; (b) `envelope.producer == token.sub`; (c) `(producer, event_type)` is in the emission allowlist; (d) `actor_type` is in the allowed set for that event type; (e) `auth_method` is consistent with `actor_type` (table below); (f) `request_id`/`trace_id` present. Any failure: 403/422 and a metric; nothing is written.

| actor_type | allowed auth_method | actor_id source |
|---|---|---|
| buyer | session+csrf, session+csrf+nonce, session+approval_token | buyer_id from session |
| merchant_shared | session+csrf | constant `merchant-demo` (disclosed) |
| reviewer_selfasserted | session+csrf | display name, UNVERIFIED |
| service | service_jwt, hmac | service slug (e.g. `agent`, `triage`) |
| system | service_jwt | `poller`, `reconcile`, `demo-clock` |
| paypal_hint | paypal_return_state | `paypal-return` (never a principal) |

Honest limit (I): audit cannot independently re-verify the USER-level actor of an outbox-delayed event, because the 60-second user token has expired by relay time. It trusts the producer's recorded actor within the allowlist. A compromised producer can mis-attribute within its own allowed set. This is a conflict with auth-gateway section 7 wording (see section 14).

Optional hardening (P2): producer also stores `act_jti`; gateway keeps a short audit-only log of minted tokens; not planned for the demo.

## 6. Event catalog

Naming: audit uses UPPER_SNAKE `event_type`; each maps from a service-map dotted event. Every entry also carries the common envelope fields (section 2.1). "Fields" below are the `payload` (per-type JSON Schema in `contracts/events/audit-<TYPE>.v1.json`; unknown keys rejected). Money = integer minor units + ISO currency. No secrets, no raw free text, no raw prompts.

Common refs when known: `buyer_id`, `mandate_id`, `order_id`, `case_id` (go into `refs` and columns).

### Mandate
| event_type | source event / producer | actor | payload fields |
|---|---|---|---|
| MANDATE_SIGNED | `mandate.signed` / mandate | buyer (session+csrf+nonce) | `mandate_id`, `mandate_hash`, `policy_version`, `nonce`, `max_total`, `currency`, `merchant_ids[]`, `expires_at`, `protection_terms` (type, cap, deadline day count as given by terms), `hmac_key_id` (id only) |
| MANDATE_REVOKED | `mandate.revoked` / mandate | buyer | `mandate_id`, `mandate_hash`, `revoked_at`, `reason_code` |
| MANDATE_EXPIRED | `mandate.expired` / mandate | system | `mandate_id`, `mandate_hash`, `expired_at` |

### Cart
| event_type | source | actor | payload fields |
|---|---|---|---|
| CART_PROPOSED | `cart.proposed` / shopping-agent | service `agent` | `proposal_id`, `mandate_id`, `lines[]` ({sku, qty}), `proposal_hash`, `catalog_version`, **AI block**: `model_id`, `prompt_version`, `input_hash`, `output_hash`, `validation_result` (ok/schema_fail/...), `status` |
| CART_CHECKED | `cart.checked` (result allow) / checkout | buyer or service | `cart_id`, `mandate_id`, `mandate_hash`, `proposal_hash?`, `server_total`, `currency`, `checks[]` ({code, result PASS/FAIL, reason_code}), `intent_fit` (PASS/NEEDS_BUYER_CONFIRMATION/REJECT_WITH_REASON/ERROR), `intent_fit_ai` AI block if used |
| CART_BLOCKED | `cart.checked` with any hard block / checkout | buyer or service | same as CART_CHECKED plus `blocked_reasons[]` (hard-block codes e.g. PRICE_MISMATCH, MANDATE_REVOKED, over cap); `fail_closed` bool when a dependency was unreachable |

Mapping rule: audit derives CART_BLOCKED vs CART_CHECKED from the producer's `cart.checked` payload (`blocked` flag), so the producer emits one event type.

### Order
| event_type | source | actor | payload fields |
|---|---|---|---|
| ORDER_CREATED | `order.created` / checkout | buyer | `order_id`, `cart_id`, `mandate_id`, `mandate_hash`, `proposal_hash?`, `total`, `currency`, `paypal_order_id`, `paypal_request_id`, `custom_id` (= mandate_id), `invoice_id` (= order_id) |
| ORDER_CAPTURED | `order.captured` / checkout | buyer (via return state) | `order_id`, `mandate_id`, `mandate_hash`, `paypal_order_id`, `paypal_capture_id`, `capture_request_id?`, `total`, `currency`, `protected_until_demo` (demo window, not PayPal's), `return_state_checked` bool |
| ORDER_CAPTURE_FAILED | `order.capture_failed` / checkout | service | `order_id`, `paypal_order_id`, `state` (CAPTURE_UNKNOWN/CANCELLED_REVOKED/FAILED), `reason_code` |
| PAYPAL_CALL_RECORDED | `paypal.call_recorded` / paypal-adapter | service `paypal-adapter` | `op` (create_order/get_order/capture/add_tracking/refund/get_refund), `paypal_request_id`, `request_body_hash`, `http_status`, `paypal_resource_id` (order/capture/refund id), `caller_service`, `decision_id?` |

### Tracking (SIMULATED CARRIER, label carried in payload)
| event_type | source | actor | payload fields |
|---|---|---|---|
| TRACKING_CREATED | `shipment.created` / tracking | merchant_shared | `shipment_id`, `order_id`, `paypal_capture_id`, `tracking_number_hash`, `carrier_label` = `SIMULATED CARRIER`, `promised_by` |
| TRACKING_STATUS_CHANGED | `shipment.status_changed` / tracking | merchant_shared or system (demo clock) | `shipment_id`, `order_id`, `from`, `to`, `forced` bool, `clock_offset_applied` |
| TRACKING_LATE_DETECTED | `shipment.late_detected` / tracking | system `poller` | `shipment_id`, `order_id`, `detector_run_id`, `kind`=LATE, `promised_by`, `evaluated_at` |
| TRACKING_LOST_DETECTED | `shipment.lost_detected` / tracking | system `poller` | as above with `kind`=LOST |
| TRACKING_CLOCK_ADVANCED | demo-control call (tracking emits `shipment.status_changed`; clock advance is audited by gateway/tracking as its own event, name I - needs tracking owner confirmation) | merchant_shared/operator | `offset_before`, `offset_after` |

### Case / triage
| event_type | source | actor | payload fields |
|---|---|---|---|
| CASE_OPENED | `case.opened` / resolution | system or buyer | `case_id`, `order_id`, `mandate_id`, `origin` (DETECTOR/BUYER_REPORT), `kind?`, `report_text_hash?` (hash only, text untrusted and not stored here) |
| CASE_TRIAGED | `case.triaged` + `triage.completed` / resolution, triage-ai | service `triage` | `case_id`, `category` (enum), `confidence`, `route` (OFFER/APPROVAL/HUMAN_REVIEW), **AI block** (`model_id`, `prompt_version`, `input_hash`, `output_hash`, `validation_result`, `injection_suspected?`); `fail_closed` bool |
| CASE_STATE_CHANGED | case transitions / resolution | per transition | `case_id`, `from`, `to` (state names from brief), `reason_code` |
| CASE_RESOLVED | `case.resolved` / resolution | service | `case_id`, `outcome` (RESOLVED_REFUNDED/RESOLVED_RESHIP/DECLINED/CLOSED), `decline_reason_code?` (human-entered declines carry a reviewer actor) |
| TRIAGE_COMPLETED | `triage.completed` for draft/brief calls / triage-ai | service `triage` | `task` (classify/draft/brief), AI block, `gate_result` (regex gate pass/reject) |
| DRAFT_GENERATED | (same as TRIAGE_COMPLETED with task=draft) | service | folded into TRIAGE_COMPLETED to keep the catalog small |

### Offer / approval
| event_type | source | actor | payload fields |
|---|---|---|---|
| OFFER_CREATED | `offer.created` / resolution | service | `offer_id`, `case_id`, `mandate_id`, `mandate_hash`, `amount`, `currency`, `basis` (INSIDE_TERMS), `policy_decision_id`, `policy_rules_hit[]` (codes), `proposal_hash` |
| OFFER_ACCEPTED | resolution | buyer | `offer_id`, `case_id`, `proposal_hash` |
| OFFER_DECLINED | resolution | buyer / reviewer_selfasserted | `offer_id`, `case_id`, `reason_code` |
| OFFER_OVERRIDE_CREATED | merchant override creates NEW offer / resolution | merchant_shared | `offer_id`, `supersedes_offer_id`, `case_id`, `amount`, `currency`, `proposal_hash`, `reason_code` |
| APPROVAL_REQUESTED | resolution | service | `approval_id`, `case_id`, `proposal_hash`, `expires_at` (token itself NEVER stored) |
| APPROVAL_GRANTED | `approval.granted` / resolution | buyer (session+approval_token) | `approval_id`, `case_id`, `proposal_hash`, `token_hash_prefix?` (non-secret id only) |
| APPROVAL_REPLAY_BLOCKED | resolution | none/buyer | `approval_id`, `proposal_hash`, `reason_code` |
| APPROVAL_DENIED | resolution | buyer | `approval_id`, `case_id`, `proposal_hash` |

### Refund
| event_type | source | actor | payload fields |
|---|---|---|---|
| REFUND_REQUESTED | `refund.requested` / resolution | service | `refund_attempt_id`, `case_id`, `order_id`, `mandate_id`, `mandate_hash`, `proposal_hash`, `amount`, `currency`, `paypal_capture_id`, `paypal_request_id` (persisted BEFORE call), `invoice_id?`, `checks[9]` (ordered: {n 1..9, code, result PASS/FAIL/ERROR, reason_code}), `basis` (offer_id or approval_id) |
| REFUND_COMPLETED | `refund.completed` / resolution | service | `refund_attempt_id`, `paypal_refund_id`, `paypal_request_id`, `status` (as returned: COMPLETED/PENDING), `amount`, `currency`, `capture_status_after?` |
| REFUND_FAILED | `refund.failed` / resolution | service | `refund_attempt_id`, `paypal_request_id`, `http_status`, `paypal_error_name` (e.g. REFUND_AMOUNT_EXCEEDED, DUPLICATE_INVOICE_ID; V behaviors), `route` = HUMAN_REVIEW |
| REFUND_UNKNOWN | `refund.unknown` / resolution | service | `refund_attempt_id`, `paypal_request_id`, `cause` (409 in-progress/timeout), `reconcile_due_at` |
| REFUND_RECONCILED | reconcile result / resolution | system `reconcile` | `refund_attempt_id`, `paypal_refund_id?`, `resolved_to` (COMPLETED/FAILED), `lookup_via` (get_refund/get_capture) |

Check results: the 9 checks are owned by `resolution`; audit stores whatever `{n, code, result, reason_code}` array the producer sends and REQUIRES `n` = 1..9 contiguous with unique codes and `result` in the enum; it does not know their names (names I: not enumerated in the docs read; check #1 is the freeze flag per threat-model section 10). Rejects arrays not of length 9 for REFUND_REQUESTED.

### Operational
| event_type | source | actor | payload fields |
|---|---|---|---|
| KILL_SWITCH_TOGGLED | freeze owner | operator (reviewer role class, I) | `flag` (REFUNDS_FROZEN/...), `to`, `reason_code`, `scope` |
| RATE_LIMITED | gateway (`rate_limited`, auth-gateway section 2) | system | `route_class`, `actor_id_or_ip_hash` |
| CHAIN_GENESIS | migration | system | see section 4 |

### Redaction rules
- Never in payload: PayPal client id/secret, tokens, approval tokens, session ids, cookies, passwords, API keys, emails, names, addresses, raw prompts/outputs, raw buyer free text. Only hashes and ids.
- Schema allowlist enforces keys; a unit test feeds secret-looking strings (`Bearer `, `sk-`, `eyJ`-prefix JWTs, `client_secret`) to every type and expects rejection.

## 7. Verify algorithm
1. Read `head_seq = max(seq)` at start (snapshot); all checks bounded by `head_seq` so concurrent appends don't matter.
2. Stream rows in `seq` order in keyset chunks (`seq > :last ORDER BY seq LIMIT :chunk`, chunk size config), each chunk its own short read txn (works with pooled endpoint).
3. For each row: (a) `seq == expected` (gapless; first must be 1 and `event_type == CHAIN_GENESIS`, `prev_hash` zeros); (b) `prev_hash == previous.row_hash`; (c) recompute `row_hash` from `canonical`; (d) parse `canonical`; confirm column copies (event_id, type, actor, refs, recorded_at) and `payload` JSONB equal the parsed content; (e) `chain_id` consistent.
4. Return first failure with reason code, or ok with `{checked, head_seq, head_hash}`.
5. Optional anchor check: row at `anchor_seq` must have `row_hash == anchor_hash`; also `head_seq >= anchor_seq` (truncation shows as head_seq < anchor_seq or hash mismatch).
6. Cost O(n); at demo volume small. Time is recorded in `verify_runs`. Cap on rows per call is config; larger chains use `from_seq` plus trusted `from_hash` (client supplies a previous anchor).

## 8. Role and grant design on Neon

Roles (created by the migrator; names are config-free constants):
| role | purpose | privileges |
|---|---|---|
| `audit_owner` | owns schema `audit` and its tables; used only by migrations/CI, never in the running service | all on schema `audit`; credentials only in CI secret store / local |
| `audit_app` | runtime role for the service | `USAGE` on schema; `INSERT, SELECT` on `entries`, `verify_runs`, `head_exports`; no `UPDATE`, `DELETE`, `TRUNCATE`, `REFERENCES`, `TRIGGER`, no `CREATE` on schema; no membership in owner role |
| `audit_reader` (P2) | read-only for the standalone verifier export / demos | `USAGE`, `SELECT` on `entries` |
Other services' roles have NO privilege on schema `audit` (ADR-004: no cross-schema SQL).

Hardening statements (described, applied in migration):
- `REVOKE ALL ON SCHEMA audit, ALL TABLES IN SCHEMA audit FROM PUBLIC`; explicit `GRANT` list above. `ALTER DEFAULT PRIVILEGES` so future tables don't leak.
- `REVOKE CREATE ON SCHEMA public FROM PUBLIC` for the database (Postgres 15+ default already, V per PG docs) and `audit_app` search_path pinned to `audit` (avoids search-path hijack).
- Triggers on `entries`: (1) `BEFORE UPDATE OR DELETE ... FOR EACH ROW` raises `audit_is_append_only`; (2) `BEFORE TRUNCATE ... FOR EACH STATEMENT` raises; (3) `BEFORE INSERT` linkage check (section 3). Trigger functions are owned by `audit_owner`, `SECURITY INVOKER`, with fixed `search_path`.
- Because `audit_app` lacks `TRIGGER` privilege and ownership, it cannot disable or drop triggers (`ALTER TABLE ... DISABLE TRIGGER` requires ownership).
- `DROP`/`ALTER` by the owner is possible: that is the honest limit.

Neon specifics (I - day-1 spike S1-3 must confirm each):
- Neon lets you create additional Postgres roles via SQL/console/API; the default project owner role is not a true Postgres superuser but is in Neon's `neon_superuser` group (VC from Neon docs; verify).
- Roles created in SQL have login ability and password; passwords never in docs or repo; connection strings only in platform env.
- Use branch-based scratch copies for the tamper demo (Neon branches, 10 per project on free, V per deployment doc), or a local docker Postgres.
- Neon PITR on free is 6 h (V per deployment doc): not a backup of record.

Env `PS_AUDIT_DATABASE_URL` points to the pooled endpoint with `audit_app`; `PS_AUDIT_MIGRATE_DATABASE_URL` (CI only) points to the direct endpoint with `audit_owner`. They must never be set together in the runtime env (startup check refuses if the migrate URL is present).

## 9. Indexing for the AG Grid view

Table is small at demo volume (I), so index for correctness of plans and sort/filter patterns, not for scale; avoid write amplification on the serialized append path (each extra index costs inside the lock).

| index | serves |
|---|---|
| PK `seq` | default sort (newest first = seq DESC), head lookup, range paging for unfiltered pages (seq is gapless, so rows `startRow..endRow` = seq range) |
| UNIQUE `event_id` | idempotency |
| UNIQUE `prev_hash`, UNIQUE `row_hash` | fork guard, lookup by hash |
| `(mandate_id, seq DESC)` partial `WHERE mandate_id IS NOT NULL` | per-mandate trail, buyer scoping |
| `(order_id, seq DESC)` partial | per-order trail |
| `(case_id, seq DESC)` partial | per-case trail |
| `(buyer_id, seq DESC)` partial | buyer role scoping (BOLA guard, every buyer query) |
| `(event_type, seq DESC)` | type filter |
| `(actor_type, actor_id, seq DESC)` | actor filter |
| `(request_id)` | find all entries of one request |
Skipped: BRIN/time index until measured (grid time filter uses `recorded_at` range combined with seq order; seq order and time order coincide because both are assigned under the lock; if the time range is the only filter, planner can use PK range with a `recorded_at` check, verify with EXPLAIN ANALYZE in test T-AU-15). No GIN on `payload` in v1 (free text search not needed; add `jsonb_path_ops` only if the grid needs payload filters).

Query pattern (grid, server-side row model): `WHERE <role scope> AND <filters> ORDER BY seq DESC LIMIT :n OFFSET :start` for small offsets, or keyset `seq < :cursor`; page size capped. `SELECT` only listed columns (no `canonical` in list view). EXPLAIN ANALYZE of the 5 main grid queries is a definition-of-done item; Seq Scan acceptable on tiny tables if the plan is documented.

Role scope appended by the service from the verified principal (never from query params): buyer `buyer_id = :principal`; merchant event-family allowlist; reviewer/operator none.

## 10. Head export for anchoring
- `GET /audit/head` -> `{chain_id, seq, row_hash, count, recorded_at, canonical_version, signature?, key_id?}` plus `paste` string: `safepayai-audit-head v1 chain=<chain_id> seq=<n> hash=<64hex> at=<ts>`.
- Signature (P1): Ed25519 over the paste string with `PS_AUDIT_HEAD_SIGNING_KEY`; public key in repo `docs/audit-head-pubkey`. A DB-only attacker cannot forge a signature for a past head; an attacker with the service env can.
- Procedure (README + runbook): export before recording the video, again right before submission, paste into the submission text and commit to a repo file `docs/anchors.txt`. Anyone then runs `scripts/verify_chain_standalone.py` on the exported chain, or `GET /audit/verify?anchor_seq=&anchor_hash=`.
- Value of the anchor is bounded by who trusts its timestamp (Devpost submission, GitHub commit time): evidence, not proof.

## 11. Honest limits
- Tamper-EVIDENT only. A superuser/`audit_owner`/platform operator can: edit rows and recompute all later hashes; truncate the tail; swap the whole table. Verify then PASSES. Only an anchor taken before the rewrite (or a signed head) exposes it.
- Rows after the last anchor are not externally pinned.
- The log records what the system wrote; it does not prove the buyer clicked (HMAC mandates, session-based; no buyer-held key). No non-repudiation.
- Actor of outbox-delayed events is producer-attested (section 5).
- `occurred_at` is producer clock; only `recorded_at` is audit's clock.
- Demo clock (tracking) makes `occurred_at` and business dates simulated; entries mark `forced`/clock offsets.
- Neon free has no managed backup of record (PITR 6 h, V); losing the DB loses the log unless exported (section 12).
- Verification ensures internal consistency; it cannot detect events that were never emitted (a bypassing producer).

## 12. Tamper demo (scratch copy only)
Never on the live chain.
1. Create a scratch copy: Neon branch of the audit DB (or `pg_dump` of `audit` schema into local docker Postgres). Run the demo against a connection string for the scratch DB with the OWNER role (to simulate a privileged attacker).
2. Step A (app role cannot): as `audit_app` run `UPDATE`/`DELETE`/`TRUNCATE` -> denied (permission error) and trigger names asserted.
3. Step B (owner can, verify catches it): as owner `ALTER TABLE entries DISABLE TRIGGER USER;` then mutate one payload field (or `canonical` amount) -> `GET /audit/verify` on the scratch service -> `HASH_MISMATCH` at that seq. Variants: edit only `payload` copy -> `PAYLOAD_MISMATCH`; delete middle row -> `SEQ_GAP`/`PREV_MISMATCH`; swap two rows; truncate tail -> verify says ok but anchor check says `ANCHOR_SEQ_BEYOND_HEAD`.
4. Step C (sophisticated attacker): script recomputes all hashes after the edit using the public algorithm -> verify PASSES; anchor check against the exported head FAILS. This is the honest-limit moment shown in docs, not hidden.
5. Output: `scripts/tamper_demo.py --scratch-url ...` prints a table of mutation -> detected? -> by which check. The script refuses to run if the target URL matches the configured production host (guard) or if `PS_AUDIT_ENV=prod`.

## 13. Retention, backup, export
- Retention: keep everything for the hackathon (no delete path exists; deletion would break the chain). Size budget: Neon free storage 1 GB per project (V) shared with all services; audit rows are small; storage is tracked in `/readyz` details (row count only, no extra queries beyond `count` via head seq).
- Policy post-event (I): if the log must shrink, cut a new chain generation: export, anchor final head of generation N, start generation N+1 with genesis referencing it (`payload.previous_chain_head`). Not implemented in v1.
- Export: `GET /audit/export?from_seq=&to_seq=` streams NDJSON of full rows (`canonical` + hashes) for the standalone verifier; nightly/manual export to a private artifact via GitHub Actions (artifact retention not verified, I). Exports contain no secrets by construction (section 6).
- Backups: do not rely on Neon PITR 6 h (V); keep a periodic NDJSON export + the anchors. Restore = recreate table from export then verify.

## 14. Conflicts and decisions (service-map.md and adr.md win)
| # | conflict | resolution |
|---|---|---|
| C1 | service-map `audit` exposes `POST /append`, `GET /entries`, `GET /verify`; auth-gateway routes `/audit/verify`, `/audit/records`. | Service-internal paths follow service-map-style but namespaced: `POST /internal/events`, `GET /entries`, `GET /verify`, `GET /head`; gateway exposes them as `/audit/records`, `/audit/verify`, `/audit/head` (api.md). Names to confirm with gateway owner. |
| C2 | service-map: "DB role INSERT/SELECT only"; auth-gateway: "audit accepts INSERT only". | INSERT + SELECT (SELECT needed for head and idempotency under lock). |
| C3 | threat-model B9: "audit down blocks refunds (fail closed, intentional)"; overview/service-map: audit not on money path, producers queue in outbox. | Follow service-map/overview: not fail-closed for money. Only resolution's local outbox write is a precondition. Flag to security owner: if "audit-down blocks refunds" is wanted, resolution must check audit lag; not required here. |
| C4 | auth-gateway section 7: audit "rejects records whose actor_* disagree with the verified caller token". Outbox delivery means the user token is gone. | Section 5: audit checks producer token + allowlists; user actor is producer-attested. Needs acceptance by gateway/security owner. |
| C5 | auth-gateway 3.2 matrix uses service names `orchestrator`, `policy`, `carrier-sim`; service-map slugs are `checkout`, `resolution`, `tracking`. | Use service-map slugs everywhere; matrix names treated as aliases. |
| C6 | auth-gateway: audit read is "any authed, public-safe fields"; threat-model T10: buyer B reading buyer A audit -> 403/404. | Stricter wins: row-level scoping per role (section 9); `verify` and `head` open to any authed (no row data). |
| C7 | Service-map event names are dotted (`order.captured`); requested catalog is UPPER_SNAKE and includes TRACKING_*, OFFER_*, APPROVAL_*, CART_BLOCKED not in the event matrix. | Audit maps dotted -> UPPER_SNAKE; additional types require producers (resolution, tracking, checkout) to emit them: tracked as a cross-team task in sprint-tasks. Additive-only events per overview section 7. |
| C8 | threat-model suggests "chain head periodically echoed externally - optional". | Promoted to P0 export endpoint plus manual anchoring procedure (REQ-AU-041); automated external echo is P2. |
| C9 | Kill-switch auto-trip on chain-verify failure (threat model section 10) but audit has no write access to the flag. | Audit exposes verify result; a GH Actions cron calls verify and notifies; the freeze owner decides on auto-trip. |
| C10 | Brief says "9 ordered checks" without names; audit needs the array shape. | Shape fixed here (n, code, result, reason_code); names left to resolution (I). |

## 15. Config and env names (names only, no values)
| env | service | purpose |
|---|---|---|
| `PS_AUDIT_DATABASE_URL` | audit | pooled Neon URL, `audit_app` role (platform secret) |
| `PS_AUDIT_MIGRATE_DATABASE_URL` | CI only | direct URL, `audit_owner`; refused at runtime |
| `PS_AUDIT_DB_POOL_MAX` | audit | small pool size |
| `PS_AUDIT_CHAIN_ID` | audit | constant chain identifier |
| `PS_AUDIT_ENV` | audit | `dev|ci|demo|prod`; guards the tamper script |
| `PS_AUDIT_TRUSTED_ISSUERS` | audit | static trusted issuer public keys map (auth-gateway section 3.1; no network JWKS) |
| `PS_AUDIT_EMISSION_ALLOWLIST_PATH` | audit | file path of `(producer, event_type, actor_type)` allowlist |
| `PS_AUDIT_HEAD_SIGNING_KEY` | audit | Ed25519 private key (secret, optional P1) |
| `PS_AUDIT_HEAD_SIGNING_KEY_ID` | audit | key id exposed in head export |
| `PS_AUDIT_VERIFY_CHUNK` | audit | verify keyset chunk size |
| `PS_AUDIT_APPEND_MAX_RETRIES` | audit | bounded retry on lock/linkage errors |
| `PS_AUDIT_PAGE_MAX` | audit | max grid page size |
| `PS_AUDIT_INTERNAL_AUDIENCE` | audit | expected `aud` (`audit`) |
| `PS_AUDIT_LOG_LEVEL` | audit | logging |
Secret hygiene: none of these values in repo; `.env.example` has names only; `LLM_API_KEY` and `PAYPAL_*` must NOT exist in audit's env (CI env-manifest test).

## 16. Module layout (inside `services/audit/`)
`app/main.py` (FastAPI), `app/api/{events,entries,verify,head,export}.py`, `app/chain/{canonical,hashing,append,verify}.py` (pure, no I/O in canonical/hashing), `app/auth/{tokens,actors}.py`, `app/schemas/` (per-type payload models generated from `contracts/events`), `app/db/{engine,queries}.py`, `migrations/` (Alembic: roles/grants/triggers/genesis in a dedicated revision), `tests/`, `scripts/{tamper_demo,verify_chain_standalone,anchor_head}.py`.

## 17. Open items
- Day-1 Neon spike: role creation, grants, trigger-blocked owner behavior, advisory xact lock via pooler, connection limit (all I).
- Confirm with gateway owner: C1, C4, C6.
- Confirm with tracking owner: clock-advance event name.
- Public unauthenticated head endpoint (judges' convenience) is a P2 decision; default is authed.
