# shopping-agent: API

Labels V/VC/I. Machine-readable truth: FastAPI-generated OpenAPI 3.1 committed at `contracts/openapi/shopping-agent.json`; events at `contracts/events/*.v1.json`; CI fails on drift (ADR-008). This file is the human summary; semantics live in `spec.md`.

## 1. Conventions
- Callers: api-gateway (user-originated, internal JWT `aud=shopping-agent`, `act.role=buyer`) for `/propose`; `checkout` (`sub=svc:checkout`) for `/intent-fit`. Browser never calls this service directly. Deny by default: missing/invalid token 401; wrong audience/role 403.
- Headers: `Authorization: Bearer <internal JWT>`, `X-Request-Id`, `traceparent`, `Content-Type: application/json`, `Idempotency-Key` (optional; calls are safe to replay by `input_sha256` dedupe, section 6).
- Bodies `extra=forbid`. No price, total, merchant-authority, currency or payment field is ever accepted or returned by this service; any such field in a request is rejected `FIELD_NOT_ALLOWED`. Responses: `Cache-Control: no-store`.
- Buyer can only propose against a mandate they own (`buyer_id` from token; mismatch -> 404 `MANDATE_NOT_FOUND`, no existence oracle).
- Gateway exposure: `POST /propose` only. `POST /intent-fit` is service-to-service only (never routed by the gateway, 404 externally). `/internal/*` never routed externally.

## 2. Endpoints
Roles: B = buyer (owner), S = service (`svc:checkout`), SYS = system job.

| Method, path | Roles | Purpose |
|---|---|---|
| POST `/propose` | B | Intent (or form fields) -> validated cart proposal (live, cached, or form) |
| POST `/intent-fit` | S (checkout only) | Validated cart + mandate intent -> advisory verdict (tighten-only) |
| GET `/propose/{proposal_id}` | B (own) | Re-read a prior proposal (for UI refresh / retry) |
| POST `/internal/outbox/flush` | SYS | Relay `cart.proposed` now (cron-safe) |
| GET `/internal/outbox?after=seq` | S | Pull catch-up |
| GET `/healthz`, `/readyz` | none / SYS | Liveness; DB + gateway breaker state; no live LLM call |

## 3. Error model and codes
Body: `{"error":{"code":"STABLE_CODE","message":"human text","details":{}},"request_id":"..."}`. No stack traces, SQL, or internal paths.

| HTTP | Codes |
|---|---|
| 401 | `UNAUTHENTICATED` |
| 403 | `FORBIDDEN` (wrong audience/role, or buyer not owner of mandate) |
| 404 | `MANDATE_NOT_FOUND`, `PROPOSAL_NOT_FOUND` |
| 422 | `INVALID_REQUEST` (schema, intent > 500 chars, empty intent with no form fields), `FIELD_NOT_ALLOWED` |
| 429 | `RATE_LIMITED` (per-user/IP gateway limit, or per-cart call cap `PS_SHOPPINGAGENT_MAX_CART_CALLS`/`PS_SHOPPINGAGENT_MAX_FIT_CALLS` hit) |
| 503 | `MANDATE_UNAVAILABLE` (mandate summary unreadable), `CATALOG_UNAVAILABLE` (catalog unreadable) |
| 500 | `INTERNAL` |
`/propose` and `/intent-fit` return their functional outcome (`NO_PROPOSAL`, `NO_MATCH`, `AI_PAUSED`, `NEEDS_BUYER_CONFIRMATION`, `degraded:true`) as a normal `200` body, never as an HTTP error — a fail-closed result is data, not a failure (spec sec 11). Callers must treat any non-2xx as the most restrictive outcome anyway (fail closed).

## 4. POST /propose
Request (intent mode):
```json
{
  "mandate_id": "uuid",
  "mode": "intent",
  "intent_text": "birthday gift for a runner under $60",
  "catalog_snapshot_id": "cat_v7"
}
```
Request (form mode; also used automatically on fallback, section 7 of spec.md):
```json
{
  "mandate_id": "uuid",
  "mode": "form",
  "form": {"category": "fitness", "max_budget_minor": 6000, "quantity": 1, "merchant_id": null, "keywords": "runner"}
}
```
Response 200:
```json
{
  "proposal_id": "uuid",
  "status": "OK | NO_MATCH | NO_PROPOSAL | AI_PAUSED",
  "source": "live | cached | form",
  "lines": [{"sku": "RUN-SOCKS-01", "quantity": 2, "display_title": "Running socks (2-pack)"}],
  "rationale": "escaped, display-only text or template string",
  "confidence": 0.82,
  "no_match_reason": null,
  "model": "gemini-flash-lite-xxxx",
  "latency_ms": 1340,
  "badge": null,
  "trace_id": "uuid"
}
```
- `source="cached"` adds `"badge": "CACHED RESPONSE (recorded from live model run <date>)"` and `"recorded_model"`; UI must render the badge, never present a cached result as live.
- `source="form"` sets `"confidence": null` and `"model": null`.
- `lines`, `rationale`, `confidence` are the ONLY fields that may influence downstream state; `display_title` is UI convenience from catalog, never trusted for money.
- Downstream handoff is mandatory regardless of `source`: the caller (web/checkout) sends only `{sku, qty}[]` + `mandate_id` to `checkout POST /carts`, which re-prices, runs mandate `/evaluate`, then calls `/intent-fit`. This endpoint never returns a price, total, merchant or `proposal_hash`.

Codes: 200 (including `NO_MATCH`/`NO_PROPOSAL`/`AI_PAUSED` — a fail-closed result is a normal response, not an error); 401; 403; 404 `MANDATE_NOT_FOUND`; 422 `INVALID_REQUEST`, `FIELD_NOT_ALLOWED`; 429 `RATE_LIMITED`; 503 `MANDATE_UNAVAILABLE`, `CATALOG_UNAVAILABLE`.

## 5. POST /intent-fit (service caller only)
Request:
```json
{
  "mandate_id": "uuid",
  "intent_text": "birthday gift for a runner",
  "cart_lines": [{"sku": "RUN-SOCKS-01", "quantity": 2, "title": "Running socks (2-pack)", "category": "fitness"}]
}
```
Response 200 (always 200; model/provider failure is encoded in the body, never an HTTP error):
```json
{
  "verdict": "PASS | NEEDS_BUYER_CONFIRMATION | REJECT_WITH_REASON",
  "reason_code": "OK | CATEGORY_MISMATCH | QUANTITY_ODD | RECIPIENT_MISMATCH | UNCLEAR",
  "reason": "escaped, display-only text, max 200 chars",
  "confidence": 0.74,
  "advisory": true,
  "degraded": false,
  "source": "live | cached | form",
  "trace_id": "uuid"
}
```
- Preconditions: caller (checkout) MUST have already passed all mandate deterministic hard checks before calling this endpoint (spec sec 5; REQ-SA-007). This service has no hard-block input and cannot clear one.
- Floors (never PASS on any failure path): `confidence < PS_SHOPPINGAGENT_FIT_MIN_CONFIDENCE` (default 0.6), schema failure, timeout, breaker open, `PS_SHOPPINGAGENT_LLM_ENABLED=false`, or upstream `injection_suspected` flag -> `verdict="NEEDS_BUYER_CONFIRMATION"`, `degraded=true`, `source="form"`.
- The combination rule (verdict can only move PASS -> NEEDS_BUYER_CONFIRMATION -> REJECT, never clear a hard block) is enforced by `checkout`, which owns the final cart status; this response is advisory input only.

Codes: 200 only for normal and degraded outcomes; 401; 403 `FORBIDDEN` (non-`svc:checkout` caller rejected); 404 `MANDATE_NOT_FOUND`; 422 `INVALID_REQUEST`, `FIELD_NOT_ALLOWED`; 429 `RATE_LIMITED`.

## 6. GET /propose/{proposal_id}
200: same shape as the original `/propose` response (read from `proposal_log`, re-serialized; no re-validation, no new model call). 404 if not found or not owned by the caller's buyer.

## 7. Internal and health
- `GET /internal/outbox?after=seq` -> events after `seq` (pull catch-up). `POST /internal/outbox/flush` -> `{"delivered": 0, "pending": 0}`; safe to repeat.
- `GET /healthz` -> 200 `{"status":"ok"}` (no DB, no LLM call). `GET /readyz` -> 200 or 503 `{"db":"ok","config":"ok","gateway_breaker":"closed|open|half_open"}`; a 503 does not itself call any provider (REQ-SA-018). Breaker `open` does not fail readiness — the service is still able to serve `form`/`AI_PAUSED` results.

## 8. Events emitted (outbox -> audit; shopping-agent consumes none)
| Event | When | Payload (no raw buyer text, hashes only) |
|---|---|---|
| `cart.proposed` | after every `/propose` call that returns `status != NO_PROPOSAL` with `source` recorded | `proposal_id, mandate_id, kind:"cart", prompt_version, provider, model, source, input_sha256, output_sha256, validation_result, injection_suspected, latency_ms, trace_id` |
Delivery at-least-once (ADR-003); consumers (audit) dedupe by `event_id`. `/intent-fit` does not emit an event in v1 (logged to `proposal_log` only; stretch: add `fit.evaluated` if audit coverage of advisory verdicts is wanted — open question, see spec.md sec 14).

## 9. Authorization matrix (summary)
| Endpoint | buyer | merchant | svc:checkout | anon |
|---|---|---|---|---|
| POST /propose, GET /propose/{id} | own mandate only | no | no | no |
| POST /intent-fit | no | no | yes | no |
| /internal/* | no | no | yes (outbox read) | no |

## 10. Rate limits and size limits
- Gateway-enforced per-user/IP limits (auth-gateway config) plus this service's own per-cart caps: `PS_SHOPPINGAGENT_MAX_CART_CALLS` (default 2), `PS_SHOPPINGAGENT_MAX_FIT_CALLS` (default 1) — 3rd+ call in the same cart session returns 429 `RATE_LIMITED` and the caller falls back to form/`NEEDS_BUYER_CONFIRMATION`.
- `intent_text` capped at `PS_SHOPPINGAGENT_INTENT_MAX_CHARS` (500); untrusted blocks (catalog text, mandate intent text as seen by `/intent-fit`) truncated to `PS_SHOPPINGAGENT_UNTRUSTED_MAX_CHARS` (1000) before prompting.
