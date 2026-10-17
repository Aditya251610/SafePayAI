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
  **On the current live deploy (Render Profile B), the gateway's own origin already
  includes a `/gateway` mount prefix** — the real base URL is
  `https://safepayai-edge.onrender.com/gateway`, so every path below is actually
  `https://safepayai-edge.onrender.com/gateway/api/...`. A bare `/api/...` against that
  host 404s (plain FastAPI 404, not this doc's error envelope) — confirmed directly
  against the live origin. If the deployed frontend reaches the gateway through a CDN
  or reverse-proxy rule that strips `/gateway`, that rewrite is external to this
  service and isn't documented anywhere else — treat `/gateway/api/...` as the ground
  truth for the Render origin itself.
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

**The envelope is NOT one uniform shape across every route — this was tested live and
confirmed to vary by which layer produces the error.** Do not write one shared error
parser that assumes `error` is always a string and `detail`/`message`/`request_id` are
always present; branch on the route/service instead, per the table below.

### Gateway-native errors (CSRF, role, auth, idempotency, rate-limit checks)
Full 4-field shape, confirmed on `CSRF_INVALID`, `FORBIDDEN`, `UNAUTHENTICATED`:
```json
{
  "error": "SOME_CODE",
  "detail": "human-readable detail",
  "message": "same as detail (compat alias)",
  "request_id": "<uuid>"
}
```
Codes you'll actually see at this layer: `UNAUTHENTICATED` (401), `FORBIDDEN` (403),
`CSRF_INVALID` (403), `NOT_FOUND` (404), `RATE_LIMITED` (429, also sets `Retry-After`),
`IDEMPOTENCY_KEY_REQUIRED` (400, **only `error`+`message`+`request_id` — no `detail`
field**, confirmed live), `MONEY_ROUTES_DISABLED` (503), `UPSTREAM_UNAVAILABLE` (503),
`UPSTREAM_WAKING` (503, also sets `Retry-After`), `UPSTREAM_TIMEOUT` (504),
`UPSTREAM_BAD_RESPONSE` (502), `internal_error` (500).

### Pydantic validation errors (422)
Only `error`+`detail`+`request_id` — **no `message` field**. Confirmed on
`POST /mandate/mandates` with an empty body and `POST /resolution/offers/{id}/accept`.

### Proxied/passthrough errors — shape depends on the OWNING service, confirmed live
A route that proxies through to a backend service returns that service's own error
body verbatim, not renormalized to the gateway's shape. Four distinct shapes observed:

| Service | Shape | Example |
|---|---|---|
| mandate | **`error` is a nested object**, not a string | `{"error":{"code":"MANDATE_NOT_FOUND","message":"mandate not found","details":{}},"request_id":"..."}` |
| checkout | flat string `error`, but adds an extra `details:{}` key and sometimes omits `message` | `{"error":"ORDER_NOT_FOUND","detail":"order not found","request_id":"...","details":{}}` |
| resolution | **`error` is the literal string `"http_error"`** — the real code is in `detail`, not `error` | `{"error":"http_error","detail":"CASE_NOT_FOUND","request_id":"..."}` — for this service's errors, match on `detail`, not `error` |
| shopping-agent | `error` is lowercase (`"unauthenticated"`) vs. the gateway's own uppercase (`"UNAUTHENTICATED"`) — casing is not normalized on proxy | `{"error":"unauthenticated","detail":"UNAUTHENTICATED","request_id":"..."}` |
| bff (`/api/bff/*`) | only `error`+`message` — **no `detail`/`request_id`** | `{"error":"...","message":"..."}` |

If you need one generic fallback for an error shape you haven't special-cased: try
`error` as a string first, then `detail` if `error` is `"http_error"` or an object,
then show whatever human-readable text you find. There is no single field that is
reliably both present and correct across every route.

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

**A 504 `UPSTREAM_TIMEOUT` on a money route does not mean the action failed —
confirmed live, repeatedly, on a real deploy.** `POST /checkout/carts/{id}/confirm`
and `POST /checkout/orders/{id}/capture` both call out to PayPal's real sandbox API,
which can take long enough (especially on a cold Render instance) that the gateway's
own proxy gives up and returns 504 while checkout keeps working in the background and
genuinely completes the order/capture a few seconds later. **Never treat a 504 on a
money route as "nothing happened" and silently retry the POST** — the real backend
state may have already changed. Instead: `GET /checkout/orders/{order_id}` (using the
`order_id` you already have, or re-fetch the buyer's order list) to see the real
current status before deciding whether to retry, show an error, or just wait and
re-poll. This is the same reasoning the backend itself uses internally (`CREATE_UNKNOWN`
exists specifically to mean "ambiguous, reconcile, don't blindly retry").

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
| POST | `/api/mandate/mandates/preview` | buyer | yes | no | **required first step** — `POST /mandates` needs the `nonce`+`screen_text_hash` this returns; was entirely missing from the gateway until this pass (PR #103), confirmed live before and after the fix. No idempotency key: each call legitimately mints a fresh nonce. Body: `{"terms": {...}}` (same `terms` shape as sign, below) |
| POST | `/api/mandate/mandates` | buyer | yes | yes | sign a new mandate. Body: `{"terms": {...preview's normalized_terms...}, "screen_text_hash": "<from preview>", "nonce": "<from preview>"}` |
| GET | `/api/mandate/mandates/{mandate_id}` | session | — | — | **Known bug, confirmed live, not yet fixed**: a non-UUID `{mandate_id}` (e.g. literal string `preview`, which is why the missing-route bug above was so confusing to debug) returns 500 `internal_error`, not a clean 404/422. Always validate/URL-encode a real UUID client-side before calling |
| GET | `/api/mandate/mandates/{mandate_id}/terms` | session | — | — | |
| POST | `/api/mandate/mandates/{mandate_id}/revoke` | buyer | yes | — | |

**`terms` bounds, confirmed live via `TERMS_OUT_OF_BOUNDS` (422)**: `max_total_minor`
and `protection.max_refund_minor` are both capped well below what you might guess
(confirmed `500000` i.e. $5000 rejected, `100000`/$1000 accepted with
`max_refund_minor: 50000`/$500 — the exact ceiling wasn't pinned down further than
"somewhere between $1000 and $5000 total, $500 refund cap works"; don't hardcode a
number into the frontend, surface the 422 and let the buyer adjust). `expires_at` is
also bounds-checked — too far in the future (confirmed: ~2.5 months out) is rejected;
a date roughly 2 weeks out was accepted. Preview, not just sign, enforces these — catch
`TERMS_OUT_OF_BOUNDS` at the preview step, not only at sign.

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
| POST | `/api/checkout/orders/{order_id}/capture` | buyer | yes | yes | yes | **Confirmed live as the correct manual-completion path**: if the buyer's browser never makes it back to `/orders/return` (closed tab, network blip, or — as hit directly tonight — no frontend page actually listening at the configured return URL), call this directly with just the `order_id` once you know/suspect PayPal approval happened (e.g. after redirecting the buyer to `approve_url` and giving up waiting on the redirect). It re-checks PayPal's real order state and captures if approved; 409 `NOT_APPROVED` if the buyer genuinely hasn't approved yet |
| GET | `/api/checkout/orders/{order_id}` | session | — | — | | |
| GET | `/api/checkout/orders/{order_id}/receipt` | session | — | — | | 409 `RECEIPT_NOT_READY` until captured. Confirmed shape on a real captured order: `{order_id, status, amount_minor, amount_major, currency, capture_id, paypal_order_id, mandate: {mandate_id, mandate_hash}, lines: [...], checks: [...], protection: {label, window_days, protected_until_day}, disclosures: [...], remaining_cap_minor, audit: {event_id, seq}}` — `disclosures` always includes the honesty-rule strings ("Sandbox only", "Merchant-funded via PayPal refund"), render them, don't strip them |
| GET | `/api/checkout/orders` | session | — | — | | `?mandate_id=` optional for buyers (omit it to list their own orders across every mandate, newest first, `?limit=` default 20 max 100); **required** for merchant/operator. Buyer-scoped for buyers, merchant-scoped (by the caller's own `merchant_id`) for merchants, unscoped for operators |
| POST | `/api/checkout/orders/return` | buyer | yes | — | | body: `{state, token, payer_id}` from the PayPal return redirect |
| POST | `/api/checkout/orders/cancel` | buyer | yes | — | | body: `{state}` from the PayPal cancel redirect |

### Tracking (`/api/tracking/*`)
| Method | Path | Role | CSRF | Idem | Notes |
|---|---|---|---|---|---|
| POST | `/api/tracking/shipments` | merchant | yes | yes | |
| GET | `/api/tracking/shipments/{order_id}` | session | — | — | **Always 200, confirmed live** — an order with no shipments (including one that doesn't exist) returns `{"shipments":[],"events":[],...}`, never 404. Treat an empty `shipments` array as "nothing to show yet", not an error |
| GET | `/api/tracking/demo/clock` | operator | — | — | demo-mode only (404 otherwise) |
| POST | `/api/tracking/demo/clock/advance` | operator | yes | yes | demo-mode only |
| POST | `/api/tracking/demo/clock/reset` | operator | yes | — | demo-mode only |
| POST | `/api/tracking/demo/shipments/{shipment_id}/force` | operator | yes | — | demo-mode only |

"Demo-mode only" means `PS_APIGATEWAY_DEMO_MODE=false` makes these 404 `NOT_FOUND`
outright, not 403 — don't render demo-clock UI unless demo mode is actually on.
**`GET /api/ops/status`'s `demo_mode` field now reports this directly** (added since
the previous version of this doc, which incorrectly said no such endpoint existed —
see §Ops below); check that instead of inferring from a 404.

### Resolution (`/api/resolution/*`)
| Method | Path | Role | CSRF | Idem | $ | Notes |
|---|---|---|---|---|---|---|
| POST | `/api/resolution/cases/report` | buyer | yes | yes | | buyer-initiated report (vs. system-detected). **Body confirmed live: `{"order_id": "<uuid>", "text": "<free text>"}`** — not `{"reason_code": ...}`, which this route rejects with `extra_forbidden` |
| GET | `/api/resolution/cases/{case_id}` | session | — | — | | buyer sees only their own case (404 if not theirs) |
| GET | `/api/resolution/cases` | merchant or operator | — | — | | |
| GET | `/api/resolution/review/queue` | reviewer | — | — | | **No seeded `reviewer` account exists anywhere in `services/api-gateway/scripts/seed.py`** as of this pass (it seeds `merchant-*`, `operator`, an optional `buyer-persona` — no reviewer). There is currently no documented way to actually obtain a reviewer session on any deployment. Either seed one before building UI against this route, or treat it as blocked |
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

### Ops (`/api/ops/*`)
| Method | Path | Role | CSRF | Notes |
|---|---|---|---|---|
| GET | `/api/ops/status` | session | — | Real shape confirmed live (two fields beyond `refunds_frozen` were previously undocumented): `{"demo_mode": bool, "money_routes_enabled": bool, "refunds_frozen": "true"\|"false"\|"unknown", "build_id": string}`. `refunds_frozen` degrades to `"unknown"` (never a raw error) if the flag owner is unreachable or the caller isn't an operator — treat `"unknown"` as frozen in the UI |
| POST | `/api/ops/freeze` | operator | yes, purpose `ops_freeze` | `{"frozen": bool, "reason": string}`; forwards to resolution, which audits the change |
| POST | `/api/ops/tick` | `X-Tick-Secret` header, no session | — | Cron use; drives tracking's + resolution's own `/internal/tick`. 202 with `{"detector": "...", "reconcile": "..."}`, each one of `accepted\|failed\|unavailable\|unconfigured` |

### BFF (`/api/bff/*`)
| Method | Path | Role | CSRF | Notes |
|---|---|---|---|---|
| GET | `/api/bff/orders/{id}` | buyer | — | Aggregates checkout order + tracking shipment + resolution case + audit chain health into one read. 404 if the order itself isn't found/owned; the other three legs degrade to `null` individually (never fail the whole call) |
| GET | `/api/bff/merchant-queue` | merchant or operator | — | `{"cases": [...], "tracking_pending": <int\|null>}` — `cases` is every `HUMAN_REVIEW` case; `tracking_pending` is a platform-wide count of active, non-terminal shipments (`null` only if tracking is unreachable) |
| GET | `/api/bff/buyer-home` | buyer | — | `{"mandates": [...], "latest_order": {...}\|null, "active_case": {...}\|null}` — mandates is the buyer's own mandate list, latest_order their single most recent order across every mandate, active_case their most recently opened non-`CLOSED` case. Each leg individually degrades to `[]`/`null` if its upstream is unreachable, never fails the whole call |

## 8. Known gaps — do not build against these yet

- **The OpenAPI specs under `contracts/openapi/*.yaml` may be stale** relative to this
  document and the real route set in `app/routers/proxy.py` — they were not
  regenerated as part of this pass. Trust this file and the gateway source over the
  YAML until someone reconciles them.
- **Idempotency-Key values are never retried/deduped by the gateway itself** — it only
  checks the header is present, the real dedupe logic lives in each owning service.
  Reusing the same key for a genuinely different submission is a client bug, not
  something the gateway catches.
- **`GET /api/mandate/mandates/{mandate_id}` 500s on a non-UUID path param** instead of
  a clean 404/422 — confirmed live, not yet fixed. Always validate the id is a real UUID
  client-side before calling (see the mandate table above).
- **`POST /api/checkout/carts` cart-check cap math looked internally inconsistent in
  one live test**: a cart whose response showed `remaining_cap_minor_after: 200`
  (i.e. would still fit, $2 left over) was nonetheless marked `status: "BLOCKED"` with
  `mandate_evaluate` returning `OVER_CAP`. Not fully root-caused this pass — if you see
  a cart blocked as over-cap, don't assume the displayed `remaining_cap_minor_after`
  is trustworthy in that same response; re-fetch the mandate's own `remaining_minor`
  as the source of truth instead.
- **No seeded `reviewer` account** — see the resolution table above. Blocks building
  real UI for `GET /api/resolution/review/queue` until one exists.
- **A 504 on a money route is not a failure signal** — see §6. This is a correctness
  issue for any frontend code that treats a non-2xx as "the action didn't happen."
