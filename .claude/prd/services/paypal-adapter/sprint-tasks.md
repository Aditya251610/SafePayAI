# paypal-adapter: sprint tasks

Date: 2026-10-10. Labels: V verified, I inference. Aligned to `sprint-plan.md`: Sprint 1 Oct 10-16, Sprint 2 Oct 17-23 (DAY-14 CUT LINE Thu Oct 23), Sprint 3 Oct 24-30, Sprint 4 Oct 31-Nov 6 (FEATURE FREEZE Fri Nov 6), freeze/submit Nov 7-10 (code freeze Nov 9, submit Nov 10). Task IDs `PA-W<week>-<n>`; "Plan ref" = the sprint-plan row this serves. Every feature task (F) is paired with a test task (T) and a deploy task (D). Test IDs refer to `test-plan.md`. Estimates are not invented: no durations given; ordering and dates come from the plan.

## Week 1 (Oct 10-16): contracts, skeleton, order create/get/capture
Exit: PayPal order created from the HOSTED `paypal` process; buyer approves; checkout can capture; G1 (return URL on Render host) result recorded.
| ID | Feature (F) | Paired TEST (T) | Paired DEPLOY (D) | Plan ref |
|---|---|---|---|---|
| PA-W1-01 | Contracts first: `contracts/openapi/paypal-adapter.yaml` (all 8 ops, envelope, error codes), `paypal.call_recorded` event schema, ticket spec, mock server from spec | PA-T17 spec-vs-code diff in CI; generated client compiles; allowlist matrix test skeleton | Mock server in compose so checkout does not block | S1-02 |
| PA-W1-02 | Skeleton: layers (`transport`/`ops`/`paypal_client`/`store`), config with masked repr, `hosts/paypal.py`, Dockerfile, `.env.example` names, Alembic `paypal` schema (call_ledger, refund_ledger, ticket_nonces, control_flags, outbox) | PA-T03 env manifest; role-limited DB test (cross-schema SELECT denied) | First hello deploy as `paypal` process on Profile B; `/healthz`, `/readyz`, `/health` | S1-03/04 |
| PA-W1-03 | Sandbox startup guard (mode, host constant, https, fixed base_url, no redirects, ID regex) | PA-T01, PA-T02 | Guard verified in deployed env (bad-config boot fails in staging smoke); credentials set in Render env of `paypal` only | REQ-PA-002/003 |
| PA-W1-04 | `paypal_client`: token cache (memory), single-flight refresh, 401 refresh+retry once, timeouts, concurrency cap, error mapping | PA-C01, PA-C02, PA-T09 on recorded doubles; fixtures recorded from spike | Deployed; smoke does a token fetch via readiness path | S1-08 |
| PA-W1-05 | Ledger + `request_id` rules: required, IN_FLIGHT-before-call, body-hash, replay, `IDEMPOTENCY_KEY_REUSED`, local IN_PROGRESS, 409 -> IN_PROGRESS | PA-T08, PA-C04 (double) | Migration applied on Neon via deploy hook | S1-08 |
| PA-W1-06 | Internal JWT verification (EdDSA pinned, aud, exp, trusted issuers), caller allowlist, deny audited | PA-T06 (REST), deny-by-default token tests (no token/wrong aud/expired/alg none) | Trusted-issuer map in env; verified against gateway-minted tokens in hosted env | S1-03 |
| PA-W1-07 | create_order + get_order + capture_order (REST `ops` functions; ticket verify from PA-W1-08 is required before any money call is enabled) | PA-C03, PA-C04, PA-C05, PA-C20, PA-T10; live S01-S05 once (manual) | Hosted smoke creates a real sandbox order; checkout I3 integration (Day 6-7) | S1-08 |
| PA-W1-08 | Authorization tickets: HMAC verify, 9-step order, nonces, kill switch (`PS_PAYPALADAPTER_MONEY_ENABLED` + DB flag), checkout key only | PA-T04, PA-T05, PA-T07 | Keys set per service env (checkout holds its own only); manifest test in CI | spec 5 |
| PA-W1-09 | Redaction filter + response_json allowlist | PA-T12 canary test | Log review on hosted run: no secret/ticket/PayerID | S1 security gate |
| PA-W1-10 | Return URL origin allowlist (`PS_PAYPALADAPTER_PAYPAL_RETURN_URL_ALLOWED_ORIGINS`) in create_order | PA-T15 | G1: real return URL on the Render/Vercel host works (U4), recorded; allowed origins set from env | U4 |
| PA-W1-11 | MCP mount spike (U11): FastMCP mount + stateless mode vs hand-written JSON-RPC fallback decision | Spike note + one `tools/list` test | none (decision recorded) | S2-07 prep |
Week 1 note: PA-W1-07 depends on PA-W1-08; build order is 01 -> 02/03 -> 04 -> 05/06 -> 08 -> 07 -> 09/10; 11 is parallel and may slip to Week 2.

## Week 2 (Oct 17-23): capture finalization, tracking, minimal MCP, events (CUT LINE Oct 23)
Cut-line need from the adapter: create + capture + get_order work on hosted Profile B for 5 consecutive runs including one after >= 12 h idle, with events in the audit chain.
| ID | Feature (F) | Paired TEST (T) | Paired DEPLOY (D) | Plan ref |
|---|---|---|---|---|
| PA-W2-01 | Capture hardening: pre-check APPROVED/`custom_id`/amount, UNKNOWN on timeout, reconcile helper `POST /v1/reconcile/{request_id}` | PA-C06 (double + manual live, pre-approved fixture), PA-C21, PA-T10 | Hosted: real capture in smoke; token refresh after > 9 h idle (V expiry) | S2-01 |
| PA-W2-02 | get_capture with derived `refundable_remaining` (`derived` label) | PA-C13 (read side), derived-remaining unit tests | Deployed | spec 3 |
| PA-W2-03 | add_tracking (natural-key dedupe, carrier OTHER, never `status`) + get_tracking (derived id + `verified:false` fallback, U2 spike) | PA-C07, PA-C08, PA-C09, PA-C10, PA-C11 (no PATCH guard test) | Deployed; tracking service integration against hosted adapter | S2-07 |
| PA-W2-04 | MCP server minimal: create_order, get_order, capture_order + get_capture, add_tracking; per-tool allowlist; `tools/list` filtering; `docs/mcp.md` draft | PA-T06 (REST+MCP agree), PA-T13; LLM services denied; MCP client call from CI | Deploy `/mcp`; MCP client check against hosted staging | S2-07 |
| PA-W2-05 | Outbox relay + `paypal.call_recorded` (and denial event decision C10) to audit | PA-T14: dedupe on `event_id`, audit-down retention | Deploy; `/internal/outbox/flush` wired to scheduled workflow | S2-06 |
| PA-W2-06 | Inbound rate limit + outbound concurrency cap | PA-T16 | Deployed; no pinger on `paypal` (R11) | REQ-PA-042 |
| PA-W2-07 | Spike regression on double: S01-S10, S24 | PA-C01..C09, C20 all green (required gate S2); fixtures scrubbed | CI job `adapter-fast` required on main | test-strategy S2 |
| PA-W2-08 | Verify U items cheaply: U2 tracker GET, U8 not-approved error name, U9 Request-Id on tracking, U10 debug header (one live session) | Probe tests record outcomes; update spec labels I -> V only with fixture | none | spec 4.2 |
| PA-W2-09 | Cut-line rehearsal support: runbook for pre-approved order, warm-up includes `paypal` process, 5 runs incl. cold | Cut-line checklist item 1 with adapter ledger entry per run | Hosted warm-up script v1 | Oct 23 |
Cut-line fallback: if the line fails, stop PA-W2-04/08 (MCP beyond minimal, probes); keep PA-W2-01, 05, 07 only.

## Week 3 (Oct 24-30): refunds and reconciliation (the money-return half)
Exit: refund saga with resolution works on hosted; concurrency tests green; live S-suite green once manually.
| ID | Feature (F) | Paired TEST (T) | Paired DEPLOY (D) | Plan ref |
|---|---|---|---|---|
| PA-W3-01 | refund_capture: resolution key tickets, pre-checks (capture `custom_id`, currency, `PS_PAYPALADAPTER_REFUND_MAX_MINOR`, derived remaining), static `note_to_payer`, `refund_ledger` | PA-C12, PA-C13, PA-C14, PA-T11 | Deploy; `PS_PAYPALADAPTER_REFUND_MAX_MINOR` set in `paypal` env | S3-06 |
| PA-W3-02 | Ledger body-hash mismatch guard on replay (`IDEMPOTENCY_KEY_REUSED`) | PA-C15 (double proves PayPal returns original; adapter refuses) | Deployed | ADR-011 |
| PA-W3-03 | 409 -> IN_PROGRESS, UNKNOWN reconcile via get_refund / get_capture | PA-C18 (concurrent identical => 1x201 + 1x409, one ledger refund), cross-service security T1 | Deploy; resolution `/refunds/reconcile` scheduled workflow | S3-06 |
| PA-W3-04 | 422 mapping: `REFUND_AMOUNT_EXCEEDED`, `DUPLICATE_INVOICE_ID` | PA-C16, PA-C17 | Deployed; resolution sends both to HUMAN_REVIEW (integration) | S3-06 |
| PA-W3-05 | get_refund; refund PENDING handling (U1 provoke attempt, fake can emit PENDING) | PA-C19; PENDING non-final test | Deployed | spec U1 |
| PA-W3-06 | MCP: add refund_capture (alias `refund_capture` unlisted), get_refund, get_tracking; `docs/mcp.md` final; read-only demo-inspector (COULD) | PA-T06 full matrix (resolution may refund, checkout may not, LLM services none); refusal demo test | Deploy; MCP client check from CI | S3-11 |
| PA-W3-07 | Freeze flag operator endpoints (`/v1/control/*`) and `GET /v1/control/status` for resolution check #1 | PA-T07 incl. unreadable flag => frozen | Deployed; operator secret in env only | C6 |
| PA-W3-08 | Spike regression S11-S22, S25 on double; chaos C1-C7, C13, C19, C20 | PA-C10..C19, C21, PA-T18, PA-T19 | CI `adapter-chaos` required on money-path PRs | test-strategy S3 |
| PA-W3-09 | Live S-suite first full run (tiny amounts, quotas, TEST- tags) | live PA-C* green once, side-by-side report committed | `live-paypal.yml` in `sandbox` environment | S3 exit |

## Week 4 (Oct 31-Nov 6): harden, document, soak (FREEZE Nov 6)
No new endpoints, no schema changes after Nov 6.
| ID | Feature (F) | Paired TEST (T) | Paired DEPLOY (D) | Plan ref |
|---|---|---|---|---|
| PA-W4-01 | Hardening: error pages/messages fixed text, truncation of PayPal names, debug flag off check, Retry-After handling | PA-T09, PA-T16 re-run; 429 path | Config reviewed on hosted env | S4-02 |
| PA-W4-02 | Docs: adapter README, endpoint table (verified vs unverified), `docs/mcp.md` final, claims list, comparison notebook vs official `@paypal/mcp` (COULD) | Docs lint: forbidden claims grep; README commands run on fresh clone | Published with repo; no PayPal logos | S4-03 |
| PA-W4-03 | Profile A rehearsal: adapter in compose, same e2e passes | Same suite on A and B | Compose documented | S4-04 |
| PA-W4-04 | Soak: 10 consecutive hosted full runs; after 24 h idle; token refresh after > 9 h | Ledger shows exactly one effect per intent across the soak; any failure restarts count | Nightly warm-up workflow; scheduled smoke | S4-05 |
| PA-W4-05 | Secret hygiene: rotate sandbox secret before repo goes public; update `paypal` env only | gitleaks full history clean; env-manifest test PA-T03 | Rotation recorded in private log | S4-08 |
| PA-W4-06 | Live suite green within last 48 h of freeze; fixtures re-recorded if divergence | Side-by-side report final | Live job run on Nov 5-6 | S4 exit |
| PA-W4-07 | Free-tier re-check reminder (Nov 1): Render hours, Neon limits | Checklist item closed | Pinger scope confirmed (only `edge`) | S4-08 |
| PA-W4-08 | Rollback drill: previous release redeploy; freeze via `PS_PAYPALADAPTER_MONEY_ENABLED=false` and DB flag | Drill passes; ledgers intact | Documented in deployment.md | deployment.md 7 |

## Freeze phase (Nov 7-10)
- Sev1/Sev2 fixes only; final full run + gitleaks + readiness checklist Nov 8; token expiry covers recording window; tag `v1.0-submission` Nov 9; hosted check logged out Nov 10.

## What to cut first (adapter items, in order; fits sprint-plan section 7)
1. Official-MCP comparison notebook (PA-W4-02 part) and demo-inspector token (PA-W3-06 part).
2. Webhook receiver (default OFF already; never built unless time remains).
3. Probes of unverified items beyond U1/U2/U8 (PA-W2-08).
4. `get_tracking` PayPal merge (keep derived id + `verified:false`).
5. `POST /v1/reconcile/{request_id}` helper (resolution can reconcile with get_* directly).
6. MCP beyond minimal (sprint-plan cut item 11): keep REST as the PayPal surface; MCP tools limited to create_order, get_order, capture_order.
7. Inbound rate limit (keep outbound cap).
- NEVER cut (sprint-plan never-cut list): real sandbox order + approve + capture; deterministic refund with persisted Request-Id + ledger + reconcile; sandbox guard; tickets and allowlist; redaction; CI + gitleaks; honesty labels; fail-closed kill switch.
- If Oct 23 cut line fails: stop MCP expansion and probes; spend Oct 24-25 only on the failing create/capture path; refunds stay on the critical path to Day 28.

## Dependencies and handoffs
- Needs: gateway JWT + trusted issuer map (W1), checkout ticket minter (W1/W2), resolution ticket minter (W3), audit `/append` (W2), Neon `paypal_app` role (W1).
- Provides: checkout (create/capture/get), tracking (add/get tracking), resolution (refund/get + control status).
- Human review depth: deep on every adapter PR (money path); limit 3 open PRs per track.
