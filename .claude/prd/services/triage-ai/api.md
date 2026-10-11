# triage-ai: API

Labels: V verified, VC vendor claim, I inference. Monorepo note (I, locked by task brief, not in source docs): this service lives at `services/triage-ai/` in the single public monorepo (ADR-009); no separate repo. `llm-gateway` is a shared package inside the `ai` process (spec.md section 14 #1), not a service — triage-ai imports it in-process, never over HTTP.

## 0. Conventions
- Base path (internal only, no public route through api-gateway, per service-map/spec section 1): `/` at the `ai` process mount, routed by caller as `triage-ai.<env>/...` or in-process ASGI mount (Profile B).
- Auth: internal JWT, `aud=triage-ai`, issued by api-gateway/resolution's internal signer; caller allowlist = `resolution` only (REQ-TA-032). Missing/invalid/expired/wrong-aud -> 401 `UNAUTHENTICATED`. Valid token but caller not `resolution` -> 403 `FORBIDDEN_CALLER`.
- All request/response bodies: pydantic v2, `extra="forbid"`, strict. Unknown fields -> 422.
- Every response (success or fail-closed) includes `provenance {source, model, prompt_version, cached_at, latency_ms}` and `triage_id` (except `/health*`).
- Model/provider failures are NEVER transport errors: they return HTTP 200 with a fail-closed payload (spec.md section 13), so `resolution` never needs special-case error handling on the AI path.
- Error body shape (transport errors only): `{"code": "...", "message": "...", "trace_id": "..."}` — no stack traces, no internal paths (T21).

## 1. `POST /classify`
Classifies untrusted buyer text (or passes through for detector-origin cases, which skip this endpoint per spec.md section 5 step 1) into the enum + confidence, with fail-closed routing.

Request:
```json
{
  "case_id": "uuid",
  "trace_id": "string",
  "origin": "buyer_report",
  "buyer_text": "my order never arrived and it's been 2 weeks",
  "timeline": [
    {"event_id": "e1", "ts": "2026-10-01T12:00:00Z", "status": "SHIPPED", "note": null}
  ],
  "order": {
    "order_ref": "ORD-T1",
    "order_date": "2026-09-20",
    "promised_by": "2026-09-28",
    "demo_now": "2026-10-10T09:00:00Z",
    "state": "MONITORING",
    "item_titles": ["Running socks 3-pack"],
    "amount_minor": null,
    "currency": null
  }
}
```
Notes: `amount_minor`/`currency` must be null/omitted for `/classify` (never sent to the model, REQ-TA-010 analogue for classify — spec.md section 2). `buyer_text` max 4000 chars (server-side truncated to `PS_TRIAGEAI_MAX_TEXT_CHARS` before the model call); `origin=buyer_report` with empty/whitespace text fails closed with no LLM call (reason `EMPTY_INPUT`).

Response 200 (success or fail-closed; shape is identical):
```json
{
  "triage_id": "uuid",
  "category": "LATE",
  "confidence": 0.82,
  "route": "PROCEED",
  "reasons": ["OK"],
  "timeline_flags": [
    {"code": "CLAIM_LATE_BUT_ON_TIME", "severity": "WARN", "origin": "rule", "event_ids": ["e1"], "explanation": "Buyer text says late; timeline shows DELIVERED within promised_by."}
  ],
  "provenance": {"source": "live", "model": "gemini-flash-lite", "prompt_version": "v1", "cached_at": null, "latency_ms": 1180}
}
```
Fail-closed example (any of: LLM error/timeout, schema fail, `confidence < PS_TRIAGEAI_MIN_CONFIDENCE`, injection suspected, evidence not a substring, kill switch, budget exhausted, breaker open — REQ-TA-003):
```json
{
  "triage_id": "uuid",
  "category": "OTHER",
  "confidence": 0.0,
  "route": "HUMAN_REVIEW",
  "reasons": ["LLM_TIMEOUT"],
  "timeline_flags": [],
  "provenance": {"source": "rules", "model": null, "prompt_version": "v1", "cached_at": null, "latency_ms": 4002}
}
```
Status codes: 200 (always, for both proceed and fail-closed outcomes); 401/403 (auth); 422 `INVALID_REQUEST` (schema, oversize required field, bad id regex); 500 `INTERNAL` (bug, not a model/provider failure — resolution treats 5xx/timeout as its own HUMAN_REVIEW, spec.md section 13).

Events: emits `triage.completed` to the outbox (hashes, category, confidence, route, reason codes, flag codes — no raw text, REQ-TA-036).

## 2. `POST /draft`
Returns a gated message draft for buyer or merchant audiences. The model never receives or emits amounts (REQ-TA-010).

Request:
```json
{
  "case_id": "uuid",
  "trace_id": "string",
  "audience": "buyer",
  "category": "LATE",
  "outcome": "REFUND_OFFER_INSIDE_TERMS",
  "order_ref": "ORD-T1"
}
```
Response 200:
```json
{
  "triage_id": "uuid",
  "subject": "Update on your order",
  "body": "We checked your order {order_ref} and it looks late. We are offering a refund of {amount} as of {date}.",
  "placeholders_used": ["{order_ref}", "{amount}", "{date}"],
  "gate": "PASSED",
  "gate_hits": [],
  "provenance": {"source": "live", "model": "gemini-flash", "prompt_version": "v1", "cached_at": null, "latency_ms": 2210}
}
```
Fallback example (gate reject or any LLM failure -> deterministic per-(category,outcome,audience) template, REQ-TA-012):
```json
{
  "triage_id": "uuid",
  "subject": "Update on your order",
  "body": "We are checking your order {order_ref}. A refund offer may follow.",
  "placeholders_used": ["{order_ref}"],
  "gate": "REJECTED_USED_TEMPLATE",
  "gate_hits": ["G-DIGIT"],
  "provenance": {"source": "template", "model": "gemini-flash", "prompt_version": "v1", "cached_at": null, "latency_ms": 1890}
}
```
Allowlisted placeholders ONLY: `{amount}`, `{order_ref}`, `{date}`, `{buyer_name}` — filled by `resolution` using server values, never by triage-ai or the model. Status codes: same pattern as `/classify` (200 always for model-path outcomes; 401/403/422/500 for transport).

## 3. `POST /brief`
Read-only reviewer brief. No action fields exist in the schema (REQ-TA-020); figures are code-filled from request facts only (REQ-TA-021).

Request:
```json
{
  "case_id": "uuid",
  "trace_id": "string",
  "buyer_text": "arrived crushed, box was wet",
  "timeline": [{"event_id": "e1", "ts": "2026-10-01T12:00:00Z", "status": "DELIVERED", "note": null}],
  "order": {"order_ref": "ORD-T1", "order_date": "2026-09-20", "promised_by": "2026-09-28", "demo_now": "2026-10-10T09:00:00Z", "state": "HUMAN_REVIEW", "item_titles": ["Running socks 3-pack"], "amount_minor": 2499, "currency": "USD"},
  "triage": { "...": "prior ClassifyResponse, or null" },
  "policy_decision": "HUMAN_REVIEW"
}
```
Response 200:
```json
{
  "triage_id": "uuid",
  "summary": "Buyer reports DAMAGED. Timeline shows DELIVERED on 2026-10-01.",
  "key_facts": [
    {"field": "order_ref", "value": "ORD-T1", "source_field": "order.order_ref"},
    {"field": "amount", "value": "24.99", "source_field": "order.amount_minor"}
  ],
  "inconsistency_flags": [
    {"code": "CLAIM_DAMAGED_BUT_NOT_DELIVERED", "severity": "WARN", "origin": "rule", "event_ids": ["e1"], "explanation": "Buyer text says damaged; timeline shows DELIVERED."}
  ],
  "open_questions": ["Was the package inspected for water damage?"],
  "read_only": true,
  "provenance": {"source": "live", "model": "gemini-flash", "prompt_version": "v1", "cached_at": null, "latency_ms": 3400}
}
```
Fallback: any failure -> brief built entirely by code from facts, `source=template` (REQ-TA-023). `amount_minor` reaches `/brief` only, as a read-only fact; never sent to `/classify` or `/draft` (spec.md section 2).

## 4. `GET /healthz`, `GET /readyz`, `GET /health`, `GET /health/deep`
- `/healthz`: process liveness, no deps checked. 200 always if process is up.
- `/readyz`: checks DB connectivity on schema `triage` only. 200 ready / 503 `NOT_READY` if DB unreachable.
- `/health`, `/health/deep`: aliases per resolution/spec.md conflict C8 naming convention, applied here for consistency across docs that reference both naming styles; `/health/deep` also checks `llm-gateway` package reachability (kill switch state, breaker state) without making a live model call.
- No auth required on health endpoints (keep-warm pingers hit these, deployment-zero-cost.md section 1).

## 5. Error codes summary
| HTTP | code | when |
|---|---|---|
| 401 | `UNAUTHENTICATED` | missing/invalid/expired/wrong-aud JWT |
| 403 | `FORBIDDEN_CALLER` | caller not `resolution` |
| 422 | `INVALID_REQUEST` | schema invalid, extra keys, oversize required field, bad id regex |
| 500 | `INTERNAL` | genuine service bug (not LLM/provider failure) |
| 503 | `NOT_READY` | `/readyz` only, DB down |
| 200 | (fail-closed body) | LLM down/timeout/schema-fail/low-confidence/injection/kill-switch/budget/breaker-open (route=HUMAN_REVIEW or gate=REJECTED_USED_TEMPLATE) |

## 6. Events emitted
| event | trigger | payload (no raw text) |
|---|---|---|
| `triage.completed` | end of `/classify` | ids, task, category, confidence, route, reason codes, flag codes, hashes |

## 7. Not exposed (by design, service-map/ADR-010)
- No public route through api-gateway (inbound: `resolution` only).
- No outbound HTTP calls to any other service; no PayPal credentials; no MCP access (ADR-007: LLM services get no MCP access).
- No endpoint accepts or returns an amount-bearing field to `/classify` or `/draft`.
