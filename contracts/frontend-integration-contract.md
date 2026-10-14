# SafePayAI frontend integration contract

Single reference for building `services/web` (or any other UI) against the real,
currently-running backend. Every route, role, and header requirement below was read
directly from the code in `services/api-gateway/app/` as of this writing, not guessed
or copied from an older spec. If this document and the code ever disagree, the code
wins — but that should not happen; re-generate this file from `app/routers/proxy.py`
and `app/routers/auth.py` if it does.

The frontend talks ONLY to `api-gateway` (`/api/*`). It never calls any other
service directly, never sees an internal JWT, and never needs to read any other
service's source code or OpenAPI spec to build against this contract.

## 1. Base URL and transport

- All requests go to the gateway's own origin, e.g. `https://<gateway-host>/api/...`.
- Every request that carries the session cookie must be made with
  `credentials: "include"` (fetch) or `withCredentials: true` (axios) — the session
  cookie is `__Host-ps_sid`, `Secure`, `HttpOnly`, `SameSite=Lax`. JavaScript can never
  read it; that's intentional.
- CORS is enforced by `PS_APIGATEWAY_FRONTEND_ORIGINS` (comma-separated). The deployed
  frontend's exact origin must be in that list or every request will be blocked by the
  browser before it reaches the gateway at all. `allow_credentials=True` is set, so the
  frontend origin can never be `*` — it must be the real origin string.

## 2. Authentication

Two ways to get a session, both set the `__Host-ps_sid` cookie on success:

### `POST /api/auth/demo-session` → 201
No body. Creates a throwaway ephemeral buyer account and logs it in immediately — this
is the "try it without an account" path for a hackathon demo. Capped by
`PS_APIGATEWAY_MAX_EPHEMERAL_BUYERS`; returns 503 `UPSTREAM_UNAVAILABLE` if the demo is
at capacity. Rate-limited per IP (`PS_APIGATEWAY_*` auth limits).

```json
// 201 response
{
  "principal": {
    "actor_type": "buyer",
    "actor_id": "<uuid>",
    "role": "buyer",
    "display_name": "demo-buyer-xxxxxxxx"
  },
  "expires_at": "2026-...Z"
}
```

### `POST /api/auth/login` → 200
```json
{ "handle": "...", "password": "..." }
```
For merchant/operator/reviewer accounts (seeded, not self-service signup). Returns 401
`UNAUTHENTICATED` for both wrong password and unknown handle — identical in shape and
timing, don't try to distinguish them in the UI. Rate-limited per (IP, handle) pair.
Response body includes `principal.merchant_id` (see "Roles" below).

### `POST /api/auth/logout` → 204
No body, no CSRF token needed (see section 3). Requires a session.

### `GET /api/auth/me` → 200
Requires a session. Returns the current principal — call this on app load to know
who's signed in and what role to render for.
```json
{
  "actor_type": "buyer",
  "actor_id": "<uuid>",
  "role": "buyer",
  "auth_method": "session",
  "display_name": "...",
  "merchant_id": null,
  "session_expires_at": "2026-...Z"
}
```

### Roles
`buyer`, `merchant`, `operator`, `reviewer`. There is no "admin" or multi-role account —
each session has exactly one role, fixed at creation. A 403 `FORBIDDEN` response from
any route means "wrong role for this action", not "not logged in" (that's 401
`UNAUTHENTICATED`).

**Merchant accounts are real per-merchant tenants, not one shared login.** Each
merchant-role login is bound to exactly one catalog merchant id (`merchant_id`,
e.g. `mrc_trailhead`) at the account level — this is the field in `/login` and `/me`
above, and it's what `GET /api/checkout/orders` uses to scope results (see §7/§8).
A merchant session with no `merchant_id` bound (shouldn't happen for a real seeded
account) sees an empty order list, not every merchant's orders — it fails closed,
not open.

## 3. CSRF — required on every state-changing call

`GET /api/auth/csrf?purpose=general` (default `purpose` if omitted) → 200, requires a
session:
```json
{ "csrf_token": "<uuid>", "purpose": "general", "expires_at": "2026-...Z" }
```

Every `POST`/`PUT` route below (anything that isn't a plain `GET`) requires this token
sent back as a header:
```
X-CSRF-Token: <csrf_token>
```
**The token is single-use.** It is consumed (deleted server-side) the moment it's
checked — whether the request that used it succeeded or failed downstream. Fetch a
fresh one before every state-changing call; do not cache or reuse one across multiple
submissions. A missing, garbled, expired, wrong-purpose, or already-used token gets
403 `CSRF_INVALID` before the request ever reaches the role check or the upstream
service.

Token lifetime is `PS_APIGATEWAY_CSRF_TTL_S` (default 3600s) from issuance.

**Exempt from this check** (no `X-CSRF-Token` needed): `POST /api/auth/login`,
`POST /api/auth/demo-session` (no session exists yet to bind a token to),
`GET /api/auth/csrf` itself (would be circular), and `POST /api/auth/logout` (not a
meaningful CSRF target). Every other `/api/*` `POST`/`PUT` route needs it.

## 4. Error envelope (every non-2xx response)

```json
{
  "error": "SOME_CODE",
  "detail": "human-readable detail",
  "message": "same as detail (compat alias)",
  "request_id": "<uuid>"
}
```
Match on `error`, not on HTTP status or `detail`/`message` text — those are for
logs/debugging, not branching logic. Gateway-level codes you'll actually see:
`UNAUTHENTICATED` (401), `FORBIDDEN` (403), `CSRF_INVALID` (403), `NOT_FOUND` (404),
`RATE_LIMITED` (429, also sets `Retry-After`), `IDEMPOTENCY_KEY_REQUIRED` (400),
`MONEY_ROUTES_DISABLED` (503), `UPSTREAM_UNAVAILABLE` (503), `UPSTREAM_WAKING` (503,
also sets `Retry-After`), `UPSTREAM_TIMEOUT` (504), `UPSTREAM_BAD_RESPONSE` (502),
`validation_error` (422), `internal_error` (500). A proxied route can also return
whatever error code the OWNING service uses (passed through verbatim) — those are
service-specific and not reproduced here; treat any unrecognized `error` value as a
generic failure and show its `detail`.

## 5. Idempotency-Key

Every route marked **Idem** below requires an `Idempotency-Key` header (any
client-generated unique string, e.g. a UUID per logical user action — generate one
new key per distinct submit, reuse it only for automatic retries of that exact same
submit). Missing it on a route that requires it is a 400 `IDEMPOTENCY_KEY_REQUIRED`
before the request reaches upstream.

## 6. Money-route gate

Routes marked **$** are real money-moving actions (confirm cart, capture, accept
offer, approval consent, refunds-frozen toggle). If the deployment has
`PS_APIGATEWAY_MONEY_ROUTES_ENABLED=false`, these return 503 `MONEY_ROUTES_DISABLED`
regardless of role/auth — a deliberate kill switch, not a bug if you see it in a
non-demo environment.

## 7. Routes

Legend: **Role** = required session role. **CSRF** = needs `X-CSRF-Token`. **Idem** =
needs `Idempotency-Key`. **$** = money-route gated.

### Auth (`/api/auth/*`)
| Method | Path | Role | CSRF | Notes |
|---|---|---|---|---|
| POST | `/api/auth/demo-session` | none | no | 201, see §2 |
| POST | `/api/auth/login` | none | no | 200, see §2 |
| POST | `/api/auth/logout` | session | no | 204 |
| GET | `/api/auth/me` | session | — | 200, see §2 |
| GET | `/api/auth/csrf` | session | — | 200, see §3 |

### Mandate (`/api/mandate/*`)
| Method | Path | Role | CSRF | Idem | Notes |
|---|---|---|---|---|---|
| POST | `/api/mandate/mandates` | buyer | yes | yes | sign a new mandate; body = mandate's `POST /mandates` request |
| GET | `/api/mandate/mandates/{mandate_id}` | session | — | — | |
| GET | `/api/mandate/mandates/{mandate_id}/terms` | session | — | — | |
| POST | `/api/mandate/mandates/{mandate_id}/revoke` | buyer | yes | — | |

### Catalog (`/api/catalog/*`, read-only)
| Method | Path | Role |
|---|---|---|
| GET | `/api/catalog/items` | session |
| GET | `/api/catalog/items/{sku}` | session |

### Shopping agent (`/api/agent/*`)
| Method | Path | Role | CSRF | Idem |
|---|---|---|---|---|
| POST | `/api/agent/propose` | buyer | yes | yes |

### Checkout (`/api/checkout/*`)
| Method | Path | Role | CSRF | Idem | $ | Notes |
|---|---|---|---|---|---|---|
| POST | `/api/checkout/carts` | buyer | yes | yes | | create + price-check a cart |
| POST | `/api/checkout/carts/{cart_id}/confirm` | buyer | yes | yes | yes | creates the real PayPal order |
| POST | `/api/checkout/orders/{order_id}/capture` | buyer | yes | yes | yes | |
| GET | `/api/checkout/orders/{order_id}` | session | — | — | | |
| GET | `/api/checkout/orders/{order_id}/receipt` | session | — | — | | 409 `RECEIPT_NOT_READY` until captured |
| GET | `/api/checkout/orders` | session | — | — | | **requires** `?mandate_id=`; buyer-scoped for buyers, merchant-scoped (by the caller's own `merchant_id`) for merchants, unscoped for operators |
| POST | `/api/checkout/orders/return` | buyer | yes | — | | body: `{state, token, payer_id}` from the PayPal return redirect |
| POST | `/api/checkout/orders/cancel` | buyer | yes | — | | body: `{state}` from the PayPal cancel redirect |

### Tracking (`/api/tracking/*`)
| Method | Path | Role | CSRF | Idem | Notes |
|---|---|---|---|---|---|
| POST | `/api/tracking/shipments` | merchant | yes | yes | |
| GET | `/api/tracking/shipments/{order_id}` | session | — | — | |
| GET | `/api/tracking/demo/clock` | operator | — | — | demo-mode only (404 otherwise) |
| POST | `/api/tracking/demo/clock/advance` | operator | yes | yes | demo-mode only |
| POST | `/api/tracking/demo/clock/reset` | operator | yes | — | demo-mode only |
| POST | `/api/tracking/demo/shipments/{shipment_id}/force` | operator | yes | — | demo-mode only |

"Demo-mode only" means `PS_APIGATEWAY_DEMO_MODE=false` makes these 404 `NOT_FOUND`
outright, not 403 — don't render demo-clock UI at all unless you've separately
confirmed demo mode is on (there is currently no gateway endpoint that reports demo
mode status to the frontend; infer it from a 404 on first use, or wire one if needed).

### Resolution (`/api/resolution/*`)
| Method | Path | Role | CSRF | Idem | $ | Notes |
|---|---|---|---|---|---|---|
| POST | `/api/resolution/cases/report` | buyer | yes | yes | | buyer-initiated report (vs. system-detected) |
| GET | `/api/resolution/cases/{case_id}` | session | — | — | | buyer sees only their own case (404 if not theirs) |
| GET | `/api/resolution/cases` | merchant or operator | — | — | | |
| GET | `/api/resolution/review/queue` | reviewer | — | — | | |
| POST | `/api/resolution/offers/{offer_id}/accept` | buyer | yes | yes | yes | |
| POST | `/api/resolution/offers/{offer_id}/decline` | buyer | yes | yes | | body: `{reason_code: "NOT_WANTED"\|"WANT_HUMAN"\|"OTHER"}` |
| GET | `/api/resolution/approvals/{token}` | session | — | — | | tier-2 approval-link preview, pure read |
| POST | `/api/resolution/approvals/{token}/consent` | buyer | yes | yes | yes | tier-2 consent; buyer must be the case's own buyer |
| POST | `/api/resolution/cases/{case_id}/merchant-action` | merchant | yes | yes | | |
| GET | `/api/resolution/controls/refunds-frozen` | operator | — | — | | reads the kill-switch state |
| PUT | `/api/resolution/controls/refunds-frozen` | operator | yes | — | yes | toggles the kill-switch |

### Audit (`/api/audit/*`, read-only)
| Method | Path | Role |
|---|---|---|
| GET | `/api/audit/entries` | session |
| GET | `/api/audit/verify` | session |

## 8. Known gaps — do not build against these yet

- **`/api/ops/*` and `/api/bff/*` are entirely unimplemented** (501 `not_implemented`
  on every route). These were scoped as a later wave and never built. Don't call them;
  there is no fallback behavior to design around, they always 501.
- **The OpenAPI specs under `contracts/openapi/*.yaml` may be stale** relative to this
  document and the real route set in `app/routers/proxy.py` — they were not
  regenerated as part of this pass. Trust this file and the gateway source over the
  YAML until someone reconciles them.
- **Idempotency-Key values are never retried/deduped by the gateway itself** — it only
  checks the header is present, the real dedupe logic lives in each owning service.
  Reusing the same key for a genuinely different submission is a client bug, not
  something the gateway catches.
