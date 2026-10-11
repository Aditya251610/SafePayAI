# Auth Gateway and Trust Fabric (SafePayAI)

Labels: V verified, VC vendor claim, I inference/unverified. Free-tier limits NOT re-verified in this doc: all marked I; re-check before build.
Scope: demo-grade identity. Not production-secure, not non-repudiable, not compliant.

## 0. Threat model (short)
- Relying parties: buyer UI, merchant UI, reviewer UI, 6-8 internal services, PayPal sandbox.
- Blast radius of forged identity: sandbox refund or sandbox order only (no real money). Still designed as if money moves.
- Assume: any one service can be compromised; client headers are hostile; LLM output and all free text are hostile.
- Recovery path: rotate keys (sec 3.4), bump `session_epoch` (sec 6), redeploy.

## 1. Identity provider choice
| Option | Pros | Cons |
|---|---|---|
| A. Gateway-owned sessions + demo personas (RECOMMENDED) | Zero external dependency; no password DB in a public repo; no free-tier pause risk; full control of CSRF/nonce binding; ~1 small module | We own session code; not "real" auth; must be labelled demo |
| B. Supabase Auth | Hosted, JWKS, magic link; free tier exists (limits I) | Free projects may pause when idle (VC, I - re-check); extra network hop; JWT claims must still be mapped to roles; email deliverability in demo |
| C. Custom JWT login with passwords | Familiar | Password storage liability, brute-force surface, no benefit for demo |
| D. Auth0/Clerk-type | Polished | Free tier terms I; vendor lock; overkill |

Decision: **A**. Fallback upgrade path: B behind the same `Principal` interface (gateway only changes how it builds the Principal).
- Browser sessions: opaque 256-bit random session id, httpOnly + Secure + SameSite=Lax cookie (`__Host-` prefix), server-side row `sessions(sid_hash, actor_type, actor_id, role, epoch, created, expires, csrf_secret_hash)`. Store SHA-256 of sid only.
- Session TTL: buyer 2 h sliding, hard cap 8 h (I, tunable). Reviewer/merchant 1 h.
- Buyer: ephemeral per-visitor buyer account created on "Start demo" (isolates judges from each other; no PII collected). Optional name field is free text, untrusted.

### Actors
| actor_type | How authenticated | Roles/scopes | Notes |
|---|---|---|---|
| `buyer` | session cookie (persona/ephemeral) | `buyer` | Owns mandates, approvals only for own `buyer_id` |
| `merchant` | single shared demo login (session) | `merchant` | DISCLOSED: one shared login; no individual merchant accountability; audit says `merchant_shared` |
| `reviewer` | session + self-asserted display name | `reviewer` | Name is unverified text; audit stamps `reviewer_name_selfasserted`; cannot move money, only approves a queued decision path allowed by policy |
| `service` (AI) | service JWT | `svc:agent`, `svc:triage` | No PayPal creds; no write path to money |
| `service` (core) | service JWT | `svc:orchestrator`, `svc:mandate`, `svc:policy`, `svc:audit`, `svc:paypal-adapter`, `svc:mcp` | See matrix |
| `system` | service JWT, `sub=svc:poller` | internal jobs | Poller, demo-clock, reconcile job |
| `paypal` | return redirect (state-bound) / webhook (optional) | none | Never a principal; webhook = hint only, always re-fetch from PayPal |

## 2. Gateway responsibilities
### 2.1 Pipeline (order matters, fail closed)
1. Assign `X-Request-Id` (uuid4, ignore inbound) and W3C `traceparent` (accept inbound only if well-formed, else new).
2. STRIP inbound headers: `X-User-Id`, `X-Actor-*`, `X-Role*`, `X-Auth-*`, `X-Internal-*`, `Authorization` (for browser routes), `X-Forwarded-*` re-written by gateway. Never forward a client-supplied identity.
3. Authenticate: cookie -> session lookup -> `Principal`. Unknown/expired/epoch-mismatch -> 401.
4. Authorize: route table (2.2). Role mismatch -> 403. Resource ownership checked by owning service using `buyer_id` from Principal, not from body.
5. CSRF + Origin check on state-changing methods (2.3).
6. Rate limit (2.4).
7. Mint short-lived internal service token carrying the Principal (sec 3.1), forward with injected `X-Request-Id`, `traceparent`.
8. Response: security headers, no stack traces, uniform error body `{error, request_id}`.

### 2.2 Route table (public edge; paths illustrative)
| Route | Method | Roles | Upstream | Extra control |
|---|---|---|---|---|
| `/auth/demo-session` | POST | anon | gateway | Per-IP rate limit, creates buyer |
| `/auth/logout` | POST | any | gateway | Revokes session |
| `/mandates` | POST | buyer | mandate | CSRF nonce + signing flow (sec 4) |
| `/mandates/{id}` | GET | buyer(owner), reviewer, merchant(read summary) | mandate | Ownership |
| `/mandates/{id}/revoke` | POST | buyer(owner) | mandate | Stop wins (sec 6) |
| `/agent/propose-cart` | POST | buyer | orchestrator -> agent | Strict body schema; LLM budget cap |
| `/orders` | POST | buyer | orchestrator | Server derives amount/merchant/currency |
| `/orders/paypal/return` | GET | anon + state binding | orchestrator | Sec 5 |
| `/orders/{id}/problem` | POST | buyer(owner) | orchestrator -> triage | Free text untrusted, length cap |
| `/merchant/orders/{id}/tracking` | POST | merchant | orchestrator | Shared login disclosed |
| `/demo/clock`, `/demo/carrier` | POST | merchant or demo-admin | carrier-sim | Labelled SIMULATED; disabled via env flag if not demo |
| `/review/queue`, `/review/{id}/decision` | GET/POST | reviewer | orchestrator | Self-asserted name captured |
| `/approvals/{token}` | GET/POST | buyer session AND valid token | orchestrator | Sec 4.2 |
| `/audit/verify`, `/audit/records` | GET | any authed (read-only) | audit | Public-safe fields only |
| `/webhooks/paypal` | POST | anon + signature (optional) | orchestrator | Hint only; verify via PayPal API or ignore (not tested - I) |
| `/internal/*` | any | NOT exposed | - | Gateway returns 404; internal network or service-token only |

Default for any unlisted route: 404/deny.

### 2.3 Session vs bearer, CSRF, CORS
- Browser traffic: cookie session only. No tokens in localStorage (XSS-theft reduction).
- Bearer tokens: only service-to-service (sec 3) and optional MCP/CLI demo client (separate, short-lived, scope-limited demo token - I, optional).
- CSRF: (a) SameSite=Lax, (b) Origin/Referer must equal allowlisted frontend origin on POST/PUT/PATCH/DELETE, (c) double-submit token: `X-CSRF-Token` = HMAC(csrf_secret, sid || purpose || ts); sensitive actions (mandate sign, approval, revoke) require a fresh single-use nonce (sec 4).
- Cross-site hosting caveat (I): if frontend (Vercel) and gateway (other host) are on different registrable domains, cookies become third-party and SameSite=Lax breaks. Controls: put gateway behind the same site via Vercel rewrites/proxy (preferred), or use custom subdomains. Decide at deploy time.
- CORS: explicit allowlist of frontend origin(s) only; `Access-Control-Allow-Credentials: true` only with exact origin; never `*`; no CORS on `/internal`.
- Security headers: CSP (no inline script), `X-Content-Type-Options`, `Referrer-Policy: no-referrer` (the PayPal `token` appears in URLs), frame-ancestors none.

### 2.4 Rate limits (per principal, else per IP; in-memory or Redis free tier - I)
| Route class | Limit (I, starting values) |
|---|---|
| `/auth/demo-session` | 10/min/IP |
| LLM-backed (`propose-cart`, `problem`) | 6/min/session, global daily LLM budget cap with hard stop |
| Mandate sign / approvals | 5/min/session |
| Reads | 120/min/session |
| Return/webhook | 30/min/IP |
- Exceeding -> 429 with Retry-After; limit events are audited as `rate_limited`.
- Single-instance in-memory limiter is acceptable on a single free dyno (I); note it resets on restart and does not scale.

## 3. Service-to-service auth (zero cost)
### 3.1 Primary: short-lived signed service JWTs
- Issuer: gateway for user-originated calls (carries Principal), each service self-issues for service-originated calls.
- Alg: EdDSA (Ed25519) or ES256; HS256 allowed only as the fallback (3.3). Algorithm pinned by verifier; reject `none` and alg switching.
- Claims: `iss` (caller svc), `sub` (caller svc id), `aud` (single target svc), `iat`, `exp` (<= 60 s), `jti` (uuid), `req` (request_id), `act` ({actor_type, actor_id, auth_method, role} or null for pure system calls), `scope` (list), `kid` header.
- Verifier rules: `aud` == self; `exp` valid with <= 5 s skew; `kid` known; `iss` in allow-list for this route; `jti` replay cache (60 s, in-memory) for money-moving routes (I: optional elsewhere).
- Tokens never logged. A user-originated token cannot be re-used against a different `aud`.
- Public keys: each service holds a static `trusted_issuers` map (env/JSON) - no network JWKS fetch at runtime (avoids availability dependency on free tier cold starts).

### 3.2 Per-service allow-list matrix (caller -> callee; Y = allowed, all else denied)
| Caller \ Callee | mandate | policy | orchestrator | agent | triage | audit | paypal-adapter | carrier-sim | mcp | LLM provider | PayPal API |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gateway | Y(read/sign/revoke) | - | Y | - | - | Y(read/verify) | - | Y(demo only) | - | - | - |
| orchestrator | Y | Y | - | Y | Y | Y(write) | Y | Y | - | - | - |
| agent | Y(read mandate/catalog only) | - | - | - | - | Y(write own events) | - | - | - | **Y** | - |
| triage | - | - | - | - | - | Y(write own events) | - | - | - | **Y** | - |
| policy | Y(read) | - | - | - | - | Y(write) | - | - | - | - | - |
| mandate | - | - | - | - | - | Y(write) | - | - | - | - | - |
| poller (system) | - | - | Y | - | - | Y(write) | Y(read-only lookups) | Y(read) | - | - | - |
| paypal-adapter | - | - | - | - | - | Y(write) | - | - | - | - | **Y (only holder)** |
| mcp | - | - | - | - | - | - | Y (same scopes as caller) | - | - | - | - |
| carrier-sim | - | - | Y(callback event) | - | - | Y(write) | - | - | - | - | - |
Rules:
- ONLY `paypal-adapter` has `PAYPAL_CLIENT_ID/SECRET`; no other service's env contains them (checked in CI via env-manifest test).
- ONLY `agent` and `triage` hold the LLM API key and may egress to the provider. Their tokens have no scope for paypal-adapter, mandate-write, or policy.
- `agent`/`triage` outputs return to orchestrator as untrusted structured data; orchestrator validates against schema then re-derives money fields from DB.
- `paypal-adapter` accepts refund/capture only from orchestrator with `scope=money.execute` AND a `decision_id` it re-verifies against the DB (does not trust caller-supplied amounts).
- `mcp` server: exposes only the tools we build; it forwards the CALLER's scopes (confused-deputy guard); money tools require orchestrator-class scope, so an MCP client cannot refund.
- `audit` accepts INSERT only; callers cannot supply `actor_*` fields themselves (stamped from token, sec 7).

### 3.3 Fallback: shared-secret HMAC
- If asymmetric tooling is a hassle on a platform: HMAC-SHA256 over `method|path|sha256(body)|ts|aud|req_id|jti` with a per-PAIR secret (not one global secret). Window 60 s.
- Tradeoff: any holder of a pair secret can both sign and verify -> compromise of callee lets it impersonate caller to that callee only. Accept for demo; state in docs.

### 3.4 Key rotation
- `kid` per key; verifiers accept {current, previous} during overlap (24 h or one redeploy).
- Rotation steps: generate new key -> deploy public key to all verifiers -> switch signer -> remove old after max token TTL + overlap.
- Compromise: remove kid immediately; tokens die within 60 s. Rotation drill performed once before submission (planned).
- Post-quantum: alg is a parameter (`alg` in token, pinned per issuer in config); no PQ claim made.

## 4. Mandate signing and approvals (identity terms)
### 4.1 Mandate sign flow
1. Buyer UI GET `/mandates/draft-challenge` -> gateway returns `nonce` (128-bit, single-use, TTL 120 s, bound to `sid`, purpose=`mandate_sign`), stored as hash.
2. UI shows human-readable terms; buyer clicks Sign. POST with `X-CSRF-Token`, `nonce`, fields.
3. Mandate service: canonicalizes JSON (RFC 8785 JCS-style: sorted keys, no whitespace, integer minor units, UTF-8), computes `mandate_hash = SHA-256(canonical)`, includes `policy_version`, `buyer_id`(from Principal), `nonce`, `expires_at`.
4. Server computes `server_hmac = HMAC-SHA256(mandate_key, mandate_hash || buyer_id || nonce)`; stores row + hmac; consumes nonce atomically (UPDATE ... WHERE used=false).
5. Audit record: actor=buyer, auth_method=`session+csrf+nonce`, payload includes `mandate_hash`.
- Meaning (honest): the server attests "an authenticated session saw these terms and submitted them". It is NOT a buyer-held-key signature, NOT non-repudiable, NOT legally binding.
- Optional WebAuthn upgrade (I, stretch): register passkey at demo-session; sign step requires assertion over `mandate_hash` as challenge; store credential id + assertion; verify with a library. Labelled "device-bound approval (demo)". Do not claim non-repudiation even then (server could still lie about display).

### 4.2 Single-use signed approval links (bound by proposal_hash)
- Used when a refund/override is outside pre-authorized terms.
- Token = base64url( payload || sig ), payload: `v, tid(uuid), proposal_id, proposal_hash, buyer_id, purpose=approve_refund, iat, exp`; `sig = HMAC-SHA256(approval_key, payload)` (or Ed25519).
- TTL: 24 h default (I; tunable; demo can use shorter). Not a bearer-only credential: redeem requires ALSO an authenticated buyer session whose `buyer_id` matches (link leakage alone is insufficient).
- Storage: DB keeps `sha256(token)` and `tid`, never the token; row has `proposal_hash`, `status {issued, redeemed, expired, revoked}`.
- Redemption: constant-time HMAC check -> load proposal by id -> recompute canonical `proposal_hash` from current DB state; MUST equal token's `proposal_hash` (any amount/terms change invalidates) -> atomic `UPDATE status='redeemed' WHERE status='issued' AND exp>now` (single-use; replay -> 409 + audit `approval_replay_blocked`).
- Displays the exact proposal terms from DB at redemption time; buyer confirms with fresh CSRF nonce.
- Merchant override = NEW proposal with new hash and new token; old tokens revoked.
- Link in messages: AI-drafted text cannot contain URLs (regex gate); link inserted by server template only.

## 5. PayPal return-redirect handling
- Facts: sandbox returns `token` (= PayPal order id) and `PayerID` to return_url (V). Our own server receipt of that redirect NOT yet tested (I).
- Binding at order creation: server generates `state` (128-bit random), stores `return_bindings(state_hash, sid_hash, buyer_id, mandate_id, paypal_order_id, order_internal_id, exp)`; return_url = `{gateway}/orders/paypal/return?state=<state>` (PayPal appends `token`, `PayerID`). Cancel_url similar.
- On return, gateway/orchestrator checks ALL: (1) `state` found, unexpired (30 min), unused; (2) request session `sid` == bound session (if cookie missing due to cross-site redirect: show "sign in again" screen requiring same buyer_id, never auto-capture) ; (3) `token` == stored `paypal_order_id` (ignore client-supplied order identity otherwise); (4) mandate still active (not revoked/expired) -> else do NOT capture, void order, audit; (5) `PayerID` treated as opaque, not trusted for identity.
- Then server fetches order from PayPal, verifies status APPROVED, amount/currency/merchant/`custom_id` match the DB, re-runs mandate checks, THEN captures with persisted PayPal-Request-Id. `state` consumed atomically.
- Capture is idempotent; double-return/refresh returns the existing result.
- Referrer-Policy no-referrer; strip query from logs after processing.

## 6. Revocation ("stop wins")
- Mandate revoke: POST by owning buyer; writes `revoked_at` in the mandate row (single source of truth) inside a transaction; every money step (order create, capture, refund, offer issuance) re-reads mandate state at execution time (no caching beyond the request).
- Semantics: revocation blocks ALL future actions: pending approval tokens -> `revoked`; unsent offers cancelled; a not-yet-captured PayPal order is not captured. Already-completed captures/refunds are NOT reversed (we cannot un-pay; state this).
- In-flight race: refund step does final check "mandate not revoked OR refund is protection payable to the buyer?" Design choice (I, to confirm with policy owner): revocation stops NEW purchases and agent actions; already-purchased protection owed to buyer is not forfeited by revoke. Document explicitly in the mandate UI.
- Sessions: logout deletes row; `session_epoch` per actor lets us kill all sessions for an actor/role; global epoch for incident.
- Service tokens: no revocation list needed (<= 60 s TTL); kid removal for compromise.
- Approval tokens: revoke by status flip; checked on redeem.
- Kill switch: env `MONEY_ENABLED=false` read by paypal-adapter on every call; fail-closed if unreadable.

## 7. Audit identity stamping
- Gateway/service-token layer produces the ONLY trustworthy actor fields; the audit service rejects records whose `actor_*` disagree with the verified caller token (callers cannot self-assert actor of another type).
- Fields on every record: `actor_type` (buyer|merchant_shared|reviewer_selfasserted|service|system|paypal_hint), `actor_id` (buyer_id | `merchant-demo` | reviewer display name (flagged unverified) | svc id), `auth_method` (session+csrf | session+csrf+nonce | session+approval_token | service_jwt | hmac | paypal_return_state | none), `request_id`, `trace_id`, `session_id_hash` (never the sid), `source_ip_hash` (salted, I), `ts` (server clock), `prev_hash`, `record_hash`.
- LLM-originated records: `actor_type=service`, actor `agent`/`triage`, plus `model_output_hash`; never labelled as decision-maker for money.
- Hash chain per instructions of brief; chain verification endpoint; INSERT/SELECT-only DB role; triggers block UPDATE/DELETE.
- Honest limit: operator with DB owner access can rewrite everything; mitigation (I, optional): periodically publish chain head hash to the public repo/README or a gist so tampering is detectable by third parties. Not claimed as tamper-proof.
- Secrets/PII never in audit payloads (redaction filter + unit test).

## 8. Secrets and key management on free platforms
- Secrets only in platform env (Render/Vercel/Fly-style dashboards; exact free tiers I). Repo public: `.env.example` only, gitleaks pre-commit + CI, no secrets in docs.
- Separate keys by purpose: `SESSION_COOKIE_KEY`, `CSRF_KEY`, `MANDATE_HMAC_KEY`, `APPROVAL_KEY`, per-service signing keys, `PAYPAL_*` (adapter only), `LLM_API_KEY` (agent/triage only). Never reuse one key across purposes.
- Per-service env manifests in repo (names only) + CI test asserting forbidden vars are absent from other services.
- Cold-start/sleep on free tiers (I; verify): services may sleep; token TTL 60 s and 5 s skew mean clocks matter; use platform NTP; gateway retries once with fresh token.
- PayPal access token cached in adapter memory only (~9 h expiry, V); never logged or returned.
- Log redaction: Authorization, Cookie, Set-Cookie, `token`, `PayerID`, client secret, approval tokens.
- Rotation drill and a documented "leaked key" runbook (3.4).

## 9. Claims
May say:
- "Server-enforced mandate checks; AI has no credentials and no write path to money."
- "Hash-chained append-only audit log with a verification endpoint; detects modification of recorded entries by anyone without DB owner access."
- "Short-lived service tokens with audience binding; PayPal credentials isolated to one service."
- "Buyer approval via authenticated session, fresh nonce and server HMAC (demo-grade)."
- "Merchant login is a single shared demo login; reviewer name is self-asserted."
Must NOT say:
- PayPal-backed/verified/protected; legally binding; non-repudiable; compliant (SOC2/PCI/etc.); fraud-proof; production-secure; injection-proof; real carrier data; individual merchant accountability; real money; "zero trust achieved"; "tamper-proof".
- WebAuthn upgrade, if built, still not non-repudiation.

## 10. Attack scenarios and controls
| # | Attack | Control |
|---|---|---|
| 1 | Client sends `X-User-Id: other` | Header strip at edge; identity only from session; services reject requests lacking valid service JWT |
| 2 | Direct hit on internal service bypassing gateway | Service JWT with `aud` required; internal ports private where platform allows (I); otherwise token-only |
| 3 | Forged / replayed service JWT | Pinned alg, `aud`, `exp` <= 60 s, `jti` cache on money routes, kid rotation |
| 4 | Confused deputy (agent asks adapter to refund) | Allow-list matrix, scope `money.execute` only for orchestrator, adapter re-verifies decision in DB |
| 5 | Prompt injection via buyer text/catalog/carrier note causing money action | AI outputs are enum/schema only; no tool with money scope in agent/triage; deterministic policy; hard blocks not overridable by AI |
| 6 | CSRF on mandate sign/revoke/approve | Origin check, SameSite, CSRF token, single-use nonce |
| 7 | Approval link leaked or forwarded | Needs matching buyer session; single-use; hash-bound; TTL; stored as hash |
| 8 | Approval replay / proposal swap after issue | Atomic status flip; recompute `proposal_hash` at redeem |
| 9 | Return-URL forgery (attacker supplies own `token`/`PayerID`, or victim tricked into capturing attacker's order) | `state` bound to session+mandate+order; `token` must equal stored order id; server re-fetches and re-checks amount/merchant |
| 10 | Revocation race (capture after revoke) | Re-read mandate in same transaction before capture/refund; kill switch |
| 11 | Session fixation / theft | New sid on login, httpOnly cookie, `__Host-`, epoch revoke |
| 12 | Brute force / LLM cost abuse on public demo | Per-route rate limits, global LLM budget cap, ephemeral buyer isolation |
| 13 | Forged webhook | Treated as hint; never trusted without PayPal API re-fetch (webhooks untested - I) |
| 14 | Audit tampering by a compromised service | INSERT-only role, triggers, chain verify, caller-stamped actor check, optional published head hash |
| 15 | Reviewer impersonation | Name self-asserted and labelled; reviewer cannot move money; policy gates remain server-side |
| 16 | Secret leak in public repo/logs | gitleaks, env manifests, log redaction, purpose-separated keys |
| 17 | Token in URL leaked via Referer/logs | no-referrer, strip query in logs, short `state` TTL, single use |
| 18 | Cross-tenant buyer data access (IDOR) | `buyer_id` from Principal only; ownership checks in owning service; tests per route |

## 11. Open questions
- Hosting layout decides cookie topology (same-site proxy vs separate domains) - decide before build.
- Confirm "revoke vs already-purchased protection" semantics (sec 6) with product owner.
- Webhook usage (skip vs hint) pending spike; return-URL on our own server untested.
- Free-tier limits for chosen hosts/DB/Redis: verify (I).
