# paypal-adapter: PRD

Date: 2026-10-10. Labels: **V** verified (our sandbox spike 2026-10-10 or primary source), **VC** vendor/secondary claim, **I** inference/unverified. No invented numbers: where a value is a design default it is marked "default (I)" and lives in config.
Sources: `00-context-brief.md`, `architecture/{service-map,adr,overview,agent-and-mcp-design,auth-gateway,threat-model,deployment-zero-cost}.md`. Conflicts between those docs are listed in `spec.md` section 14.

## 1. Purpose
- The ONLY service that holds PayPal credentials and talks to PayPal (V by design: service-map).
- Anti-corruption layer: wraps the verified PayPal sandbox REST calls in our own DTOs; PayPal models never leak to other services.
- Hosts OUR OWN MCP server (ADR-007) over the same internal functions as the REST routes: 8 tools (create_order, get_order, capture_order, get_capture, add_tracking, get_tracking, refund_capture, get_refund).
- Money-moving tools need an HMAC-signed, single-use authorization ticket minted by `checkout` or `resolution`. LLM services (`shopping-agent`, `triage-ai`) get no access at all.
- It decides nothing: no mandate logic, no policy, no LLM. It enforces defense-in-depth invariants only.

## 2. Users (callers)
| Caller (slug) | Uses |
|---|---|
| checkout | create_order, capture_order, get_order, get_capture |
| tracking | add_tracking, get_tracking, get_order, get_capture |
| resolution | refund_capture, get_refund, get_capture, get_order, get_tracking |
| demo-inspector (optional, off by default) | read-only get_* |
| shopping-agent, triage-ai, api-gateway, web, mandate, catalog, audit | none |
- Judges/MCP clients: only via the optional read-only demo-inspector token; never via the public gateway.

## 3. Goals
- G1 One credential boundary: PayPal secret exists in exactly one service env.
- G2 Exactly-once money effects from at-least-once callers (ledger + PayPal-Request-Id; V PayPal replay behavior).
- G3 Honest, normalized error and status vocabulary so callers never parse PayPal errors.
- G4 A tested MCP surface that doubles as the "agentic commerce" demo (refusal demo: read-only token cannot refund; forged ticket rejected).
- G5 Sandbox-only by construction (startup guard).

## 4. Non-goals
- No gated PayPal products: Fastlane, Vault v3, Agent Ready, Store Sync, WebMCP, production Payouts (V gated per brief).
- No production endpoints, no real money, no live credentials. Startup refuses non-sandbox base URL.
- No tracker cancel exposed (PATCH CANCELLED is irreversible, V); no PATCH to other statuses (rejected by PayPal, V).
- No PayPal Disputes API in v1 (untested, I).
- No mandate/policy/pricing logic; no LLM calls; no email; no card data handling.
- No dependency on official `@paypal/mcp` at runtime (comparison only; untested from backend, V per brief).
- No webhook-driven state changes (webhooks are hints only, optional, default off).
- No per-merchant PayPal accounts (single shared sandbox merchant).

## 5. Requirements
Priority: M = must (cut line protects these), S = should, C = could.

### 5.1 Credentials, startup, sandbox guard
| ID | P | Requirement |
|---|---|---|
| REQ-PA-001 | M | PayPal client id/secret read only from this service's platform env; absent from every other service env (CI env-manifest test). |
| REQ-PA-002 | M | Startup guard: refuse to start unless `PS_PAYPALADAPTER_PAYPAL_MODE=sandbox` AND `PS_PAYPALADAPTER_PAYPAL_BASE_URL` host is exactly the sandbox API host AND scheme is https. Any other value: process exits non-zero with a non-secret error. |
| REQ-PA-003 | M | Egress allowlist: outbound HTTP client only to the configured sandbox host; no caller-supplied URL is ever fetched (SSRF control). |
| REQ-PA-004 | M | Kill switch: `PS_PAYPALADAPTER_MONEY_ENABLED` env and a DB freeze flag both checked on every money call immediately before the PayPal request; unreadable = frozen (fail closed). |

### 5.2 REST client
| ID | P | Requirement |
|---|---|---|
| REQ-PA-010 | M | OAuth client-credentials token cached in memory only (never DB/log); refreshed before expiry (token life ~9 h, V) with single-flight lock; on 401 refresh once and retry the same request once (V invalid token -> 401). |
| REQ-PA-011 | M | Every write requires a caller-supplied `request_id` (UUID); missing = 422 `REQUEST_ID_REQUIRED`. It is sent as `PayPal-Request-Id` unchanged. |
| REQ-PA-012 | M | Ledger row written (state IN_FLIGHT) BEFORE the PayPal call; updated after. Same `request_id` + same body hash returns the stored result without a second PayPal call; same `request_id` + different body hash returns `IDEMPOTENCY_KEY_REUSED` (PayPal itself would return the original even if the amount differs, V). |
| REQ-PA-013 | M | PayPal 409 (concurrent same Request-Id, V) maps to status `IN_PROGRESS`; never auto-retried; caller reconciles via GET. |
| REQ-PA-014 | M | Timeout/connection loss/5xx on a write maps to `UNKNOWN`; never blind-retried (the 401 retry is the only automatic write retry, because a 401 means PayPal did not process the request). |
| REQ-PA-015 | M | Normalize errors to our vocabulary (spec section 7), including 422 `REFUND_AMOUNT_EXCEEDED` and 422 `DUPLICATE_INVOICE_ID` (V). |
| REQ-PA-016 | M | Amounts accepted as integer minor units + ISO currency (USD only in demo); converted to PayPal decimal string inside the adapter; no float math. |
| REQ-PA-017 | S | Reads (GET) retry with bounded backoff on 429/5xx/timeouts; honor `Retry-After` when present (PayPal rate limits unknown, I). |
| REQ-PA-018 | M | Never send a tracker `status` at creation (ignored by PayPal, V) and never call PATCH tracker status (only CANCELLED works and is irreversible, V). |

### 5.3 Tools (REST + MCP share one code path)
| ID | P | Requirement |
|---|---|---|
| REQ-PA-020 | M | Eight tools with REST equivalents per spec section 3: create_order, get_order, capture_order, get_capture, add_tracking, get_tracking, refund_capture, get_refund. |
| REQ-PA-021 | M | create_order sets `custom_id` = mandate_id and `invoice_id` = internal order id on the purchase unit (survive onto capture, V). return_url/cancel_url are built by the caller from config and validated against an origin allowlist; no free-form URL accepted. |
| REQ-PA-022 | M | capture_order: verify via get_order that status is APPROVED and `custom_id`/amount match the ticket before calling capture; never capture on a client-supplied identity. Result unknown = `UNKNOWN` (caller reconciles with get_order; no blind recapture). |
| REQ-PA-023 | M | refund_capture: verify capture belongs to ticket's mandate (`custom_id` match, V), amount <= ticket amount, amount <= per-call ceiling from config, currency match; static `note_to_payer` template only (no model text to PayPal). |
| REQ-PA-024 | M | add_tracking: carrier `OTHER` + `carrier_name_other`, `notify_payer` default false; tracker id `{capture_id}-{tracking_number}` (V); duplicate returns existing. Documented as "tracking added" signal only; PayPal cannot hold late/lost/delivered (V). |
| REQ-PA-025 | S | get_tracking merges PayPal tracker data (path unverified, I) with a clearly labelled `SIMULATED` carrier status read from `tracking` service; if the tracker GET path is not verified by sprint cut, return our computed tracker id + `unverified` flag. |

### 5.4 Authorization ticket and access control
| ID | P | Requirement |
|---|---|---|
| REQ-PA-030 | M | Money tools (create_order, capture_order, refund_capture) require an HMAC-SHA256 signed, single-use, short-TTL authorization ticket; parameters must match the ticket exactly (spec section 5). |
| REQ-PA-031 | M | Separate HMAC keys per minter (checkout vs resolution) so a compromised `checkout` cannot mint refund tickets. |
| REQ-PA-032 | M | Per-caller tool allowlist enforced server-side before dispatch; denied = `NOT_PERMITTED` (HTTP 403) and an audit event. MCP `tools/list` shows only the caller's allowed tools; call-time check still applies. |
| REQ-PA-033 | M | Caller identity only from a verified internal service JWT (`aud=paypal-adapter`, EdDSA, pinned alg, short TTL); never from body/headers. |
| REQ-PA-034 | M | `/mcp` and `/v1/*` are not exposed through the public gateway; gateway returns 404 for `/internal/*` and has no route to the adapter (auth-gateway section 2.2). |

### 5.5 Observability, rate limiting, redaction
| ID | P | Requirement |
|---|---|---|
| REQ-PA-040 | M | Emit `paypal.call_recorded` (outbox + HTTP push to audit) for every outbound PayPal call and every denied/ticket-rejected attempt. |
| REQ-PA-041 | M | Log redaction: no client secret, access token, Authorization, tickets, `token`/`PayerID`, payer PII; allowlisted fields only; unit test with canary strings. |
| REQ-PA-042 | S | Per-caller inbound rate limit (in-memory, lower for money tools) and outbound concurrency cap (avoid Render "high outbound traffic" suspension, V). |
| REQ-PA-043 | M | `/healthz` (liveness, no PayPal call) and `/readyz` (DB + config flags; optional cached token check). |
| REQ-PA-044 | M | Propagate `trace_id`; log `paypal-debug-id` response header when present (header name VC/I). |

### 5.6 Optional
| ID | P | Requirement |
|---|---|---|
| REQ-PA-050 | C | Webhook ingestion `POST /v1/webhooks/paypal`: default OFF; if on, treat as hint only: record, emit hint event, never change state without re-fetching the resource. Signature verification unverified (I). |
| REQ-PA-051 | C | Read-only demo-inspector token for the MCP refusal demo. |
| REQ-PA-052 | C | Side-by-side notebook comparing our tool list with official `@paypal/mcp` (not in CI, not in runtime). |
| REQ-PA-053 | C | Reconcile helper `POST /v1/reconcile/{request_id}` that resolves an UNKNOWN/IN_PROGRESS ledger row by lookup (get_order/get_capture/get_refund). |

## 6. Success metrics
No numeric targets are invented; metrics are binary properties or counts to be reported from test runs.
| Metric | Definition | Target |
|---|---|---|
| Duplicate money effects | Count of double captures/refunds in replay + concurrency tests (fake and live sandbox) | 0 |
| Ledger coverage | Outbound PayPal write calls without a pre-call ledger row | 0 |
| Credential isolation | Services other than paypal-adapter whose env manifest contains PAYPAL_* | 0 (CI) |
| Non-sandbox start | Successful startups with a non-sandbox base URL | 0 (test) |
| Ticket negative tests | Forged/expired/replayed/mismatched/wrong-op tickets accepted | 0 |
| Allowlist negative tests | Disallowed (caller, tool) pairs accepted, including LLM services | 0 |
| Redaction canaries | Canary secrets found in captured logs/events | 0 |
| Verified-behavior replay | Spike behaviors (brief section 3) reproduced by contract tests on fake AND live sandbox | all listed in test-plan.md |
| Unverified items closed | Items in spec section 9 moved to V or explicitly left I with a documented fallback | report count at S4 |
| Cold-start time of `paypal` process | Measured on the chosen host | unknown until measured; report, do not claim |

## 7. Risks
| # | Risk | L/I | Mitigation |
|---|---|---|---|
| R1 | Refund returns PENDING (untested, I) and callers assume COMPLETED | M/M | Model status as COMPLETED/PENDING/FAILED; caller treats PENDING as not-final; reconcile via get_refund; test with fake; try to provoke in live sandbox. |
| R2 | Tracker GET path wrong (I) | M/L | Verify in S2 spike; fallback returns derived id + `unverified`; nothing money-critical depends on it. |
| R3 | Ticket design (signed vs callback) causes stale authorization (mandate revoked after minting) | M/H | Short TTL, minter re-reads mandate at minting time, adapter freeze flag, single-use; callback validation recommended only as optional later hardening (spec section 14). |
| R4 | Cold start of sleeping `paypal` process during demo (~1 min wake, V Render) | H/H | Profile B keep-warm, warm-up script, callers use timeouts + idempotent retry via ledger. |
| R5 | PayPal Request-Id retention window unknown (I) | L/M | Local ledger stores results; replay served from ledger regardless of PayPal retention. |
| R6 | Sandbox approve step needs a real click; live capture cannot be fully automated (V) | H/M | Capture covered by fake in CI; live capture is a manual/guided test; keep a pre-approved order recipe in runbook. |
| R7 | MCP Python SDK mount API/stateless mode differs from assumption (I) | M/M | Spike in S1; fallback is a thin hand-written JSON-RPC streamable HTTP handler for the 8 tools. |
| R8 | Secret leak via AI coding agent / public repo | M/H | gitleaks pre-commit + CI, `.env.example` names only, redaction tests, rotate before public. |
| R9 | India-based business sandbox account / buyer currency constraints (V brief) | M/M | USD only; US personal sandbox buyer for live tests. |
| R10 | Two ledgers (resolution persisted request_id + adapter call_ledger) drift | M/M | ADR-011 reconcile; `request_id` is the join key; reconcile test. |
| R11 | Free-tier Render hours/Neon compute exhaustion (V) | M/M | No second always-on service; ping only `edge`; see deployment.md. |
| R12 | Overclaiming ("PayPal-verified", "non-repudiable") | L/H | Claims list in spec section 13; docs lint. |

## 8. Honesty rules specific to this service
- Say: "sandbox only", "our own MCP server over PayPal REST", "demo-grade HMAC tickets (not non-repudiation)", "refund is merchant-funded via PayPal refund".
- Do not say: PayPal-backed/verified, official PayPal MCP, production-secure, injection-proof (money tools are unreachable by LLM by construction, which is a property of the allowlist + ticket keys, still demo-grade).

## 9. Dependencies
- Upstream: PayPal sandbox REST. Postgres schema `paypal` (call_ledger, refund_ledger, ticket_nonces, control_flags, outbox).
- Callers: checkout, tracking, resolution. Downstream push: audit (events).
- Shared libs (no business logic): internal-token verification, outbox, logging redaction, generated clients.
