# audit - API

Labels: V/VC/I. FastAPI; OpenAPI 3.1 generated and committed to `contracts/openapi/audit.json` (ADR-008). Error body (all): `{"error": "<CODE>", "message": "...", "request_id": "..."}` (auth-gateway section 2). No stack traces.

## 0. Surfaces
| surface | caller | auth |
|---|---|---|
| Internal ingestion `/internal/*` | producer services (outbox relays) | service JWT, `aud=audit`, scope `svc:audit`, `exp <= 60 s`; not routed by gateway; never browser-reachable |
| Read/verify (service paths) | api-gateway only | internal JWT minted by gateway carrying `act` (principal) |
| Public (via gateway) | web | session cookie; gateway rewrites to service paths |

Gateway public name -> service path (reconciles conflict C1):
| public (gateway) | service path |
|---|---|
| `GET /api/audit/records` | `GET /entries` |
| `GET /api/audit/records/{seq}` | `GET /entries/{seq}` |
| `GET /api/audit/verify` | `GET /verify` |
| `GET /api/audit/head` | `GET /head` |
| `GET /api/audit/export` | `GET /export` |

## 1. Ingestion

### POST /internal/events
Append one event. Idempotent on `event_id`.
Request (envelope, overview section 7 plus actor):
```json
{
  "event_id": "7c1e...-uuid",
  "type": "ORDER_CAPTURED",
  "version": 1,
  "occurred_at": "2026-10-20T14:03:11.120345Z",
  "producer": "checkout",
  "aggregate_id": "ord_123",
  "trace_id": "t_abc",
  "request_id": "r_abc",
  "actor": {"type": "buyer", "id": "buyer_77", "auth_method": "session+csrf", "session_id_hash": "ab12..."},
  "refs": {"buyer_id": "buyer_77", "mandate_id": "m_1", "order_id": "ord_123"},
  "payload": {"order_id": "ord_123", "mandate_hash": "9f...", "paypal_order_id": "5O1...", "paypal_capture_id": "3C2...", "total": 5400, "currency": "USD"}
}
```
Responses:
| code | body | meaning |
|---|---|---|
| 201 | `{"seq": 42, "row_hash": "ab..", "duplicate": false}` | appended |
| 200 | `{"seq": 42, "row_hash": "ab..", "duplicate": true}` | event_id already recorded (no new row) |
| 400 | `MALFORMED_ENVELOPE` | not JSON / missing envelope field |
| 401 | `UNAUTHENTICATED` | bad/expired service token |
| 403 | `PRODUCER_MISMATCH`, `EVENT_NOT_ALLOWED_FOR_PRODUCER`, `ACTOR_NOT_ALLOWED`, `AUTH_METHOD_MISMATCH` | actor stamping/allowlist failure (nothing written) |
| 409 | `EVENT_ID_CONFLICT` | same `event_id` but different content hash (a producer bug; never overwritten) |
| 422 | `PAYLOAD_SCHEMA_INVALID`, `FLOAT_FORBIDDEN`, `UNKNOWN_FIELD`, `SECRET_PATTERN_REJECTED`, `CHECKS_ARRAY_INVALID` | schema failure; includes `details[]` paths only (no echo of values) |
| 503 | `CHAIN_BUSY` / `DB_UNAVAILABLE` | retry later (Retry-After); producer outbox retries with backoff; cold Neon absorbed here |

### POST /internal/events/batch
Body `{"events": [ ...up to PS_AUDIT_BATCH_MAX envelopes... ]}`. One advisory lock and one commit for the batch; per-item results in order:
`{"results": [{"event_id":"..","status":"APPENDED|DUPLICATE|REJECTED","seq":43,"error":null}, ...]}`.
Atomic per request for APPENDED items: if the txn fails, none are written (503). REJECTED items (schema/actor failure) do not block valid items; they are reported (HTTP 207 style status in body, HTTP 200 overall) and producers must treat REJECTED as permanent (dead-letter, not retry).

### GET /internal/outbox-ack (not provided)
Audit emits no events; no pull endpoint.

## 2. Read API (AG Grid server-side row model)

### GET /entries
Roles: buyer (own rows), merchant (order/tracking/case/offer/approval/refund families), reviewer, operator (all). Scope is applied from the verified principal; query params can only narrow.

Query params (all optional):
| param | meaning |
|---|---|
| `startRow`, `endRow` | AG Grid block (endRow exclusive); page size = endRow-startRow, capped by `PS_AUDIT_PAGE_MAX` |
| `sort` | `seq` (default, desc) or `recorded_at`, `event_type`, `actor_id`; direction `:asc|:desc` (one sort key) |
| `event_type` | exact or comma list |
| `family` | `MANDATE|CART|ORDER|TRACKING|CASE|OFFER|APPROVAL|REFUND|AI|OPS` |
| `actor_type`, `actor_id` | exact |
| `mandate_id`, `order_id`, `case_id`, `request_id`, `trace_id` | exact |
| `from`, `to` | `recorded_at` range (RFC3339 UTC) |
| `after_seq` / `before_seq` | keyset cursors (preferred for deep paging) |

Response 200:
```json
{
  "rows": [
    {"seq": 42, "recorded_at": "2026-10-20T14:03:11.220Z", "event_type": "ORDER_CAPTURED",
     "actor_type": "buyer", "actor_id": "buyer_77", "auth_method": "session+csrf",
     "request_id": "r_abc", "mandate_id": "m_1", "order_id": "ord_123", "case_id": null,
     "summary": "Order captured 54.00 USD", "row_hash_short": "ab12cd34", "prev_hash_short": "99aa..." }
  ],
  "lastRow": 118,
  "head_seq": 140,
  "verified": {"ok": true, "head_seq": 140, "at": "2026-10-20T14:00:00Z"}
}
```
- `lastRow` is the total matching count when the final block is reached, else `-1` (AG Grid contract). Total count for unfiltered views = `head_seq` (gapless), cheap; filtered counts computed only on the last block.
- `summary` is generated server-side from payload (safe, no free text). `verified` is the last `verify_runs` row (informational).
- Errors: 400 `BAD_FILTER`, 401, 403 `ROLE_NOT_ALLOWED`, 422 invalid range. Buyer asking for another buyer's `mandate_id` gets an empty set (200, zero rows), not an error, to avoid ID probing; direct `GET /entries/{seq}` of a non-owned row is 404.

### GET /entries/{seq}
Full entry for the detail drawer: all columns above plus `payload` (parsed), `prev_hash`, `row_hash`, and `canonical` for reviewer/operator only (buyer sees `payload` and hashes, not canonical). Role scoping same as list. 404 if missing OR not visible.

### GET /entries/by-ref
`?mandate_id=` or `?order_id=` or `?case_id=` -> ordered trail (ascending seq) for one subject, max `PS_AUDIT_PAGE_MAX`; used by receipt/case pages ("show proof trail").

## 3. Verify

### GET /verify
Roles: any authenticated principal (no row data returned). Rate-limited at gateway (cost O(n)).
Query: `anchor_seq`, `anchor_hash` (optional), `from_seq`, `from_hash` (optional trusted start).
Response 200 (always 200; `ok` carries the verdict):
```json
{"ok": true, "chain_id": "ps-demo-1", "checked": 140, "head_seq": 140, "head_hash": "ab..", "algorithm": "sha256/v1", "duration_ms": 87,
 "anchor": {"checked": true, "ok": true}}
```
Failure:
```json
{"ok": false, "first_bad_seq": 57, "reason": "HASH_MISMATCH", "expected": "..", "found": "..", "checked": 57, "head_seq": 140,
 "anchor": {"checked": false}}
```
`reason` in: `HASH_MISMATCH`, `PREV_MISMATCH`, `SEQ_GAP`, `PAYLOAD_MISMATCH`, `GENESIS_MISSING`, `CHAIN_ID_MISMATCH`, `ANCHOR_HASH_MISMATCH`, `ANCHOR_SEQ_BEYOND_HEAD`.
Errors: 401; 429 (gateway); 503 `DB_UNAVAILABLE`. A failed verify is a normal 200 (the UI shows red); gateway/alerts key off `ok`.
Side effect: one `verify_runs` INSERT (informational).

### GET /verify/last
Latest `verify_runs` row (cheap; used by the grid header).

## 4. Head export

### GET /head
Roles: any authenticated. Response 200:
```json
{"chain_id": "ps-demo-1", "seq": 140, "row_hash": "ab..64hex", "count": 140,
 "recorded_at": "2026-10-20T14:03:11.220345Z", "canonical_version": 1,
 "paste": "safepayai-audit-head v1 chain=ps-demo-1 seq=140 hash=ab..64hex at=2026-10-20T14:03:11.220345Z",
 "signature": "base64...", "key_id": "k1"}
```
`signature`/`key_id` present only when `PS_AUDIT_HEAD_SIGNING_KEY` configured. Inserts a `head_exports` row. This is the string to paste into the submission/repo.

## 5. Export (NDJSON)

### GET /export
Roles: reviewer, operator. Params `from_seq`, `to_seq` (default 1..head). `Content-Type: application/x-ndjson`; one full row per line (`seq, canonical, prev_hash, row_hash, ...`), max rows per call config. Consumed by `scripts/verify_chain_standalone.py`. No secrets by construction.

## 6. Health
| path | auth | behavior |
|---|---|---|
| `GET /healthz` | none | liveness, never touches DB (keeps Neon asleep, protects CU-hours) |
| `GET /readyz` | none (no sensitive data) | DB reachable (`SELECT 1`), genesis present (cached after first success), trusted issuers loaded; returns 503 with flags otherwise. Used by warm-up, not by 5-min pingers. |

## 7. Endpoint x role matrix
| endpoint | buyer | merchant | reviewer | operator | service (producer) |
|---|---|---|---|---|---|
| POST /internal/events(/batch) | - | - | - | - | yes (own allowlist) |
| GET /entries | own rows | order-side families | all | all | - |
| GET /entries/{seq} | own | order-side | all (+canonical) | all (+canonical) | - |
| GET /entries/by-ref | own subject | order-side | all | all | - |
| GET /verify, /verify/last, /head | yes | yes | yes | yes | - |
| GET /export | - | - | yes | yes | - |
Operator = reviewer class with the separate operator role defined by the freeze design (threat-model section 10); exact role string owned by gateway (I).

## 8. Events emitted/consumed
- Emits: none.
- Consumes: all catalog events (spec section 6) via `POST /internal/events[/batch]`. Mapping from dotted service-map events to UPPER_SNAKE types is in spec section 6 and C7.

## 9. Rate and size limits
- Envelope body size cap and `PS_AUDIT_BATCH_MAX` are config (values I, unset). Request timeout generous on first call after Neon wake; producers use backoff.
- Gateway rate-limits `/verify` and `/export` more tightly than `/entries` (values owned by gateway).
