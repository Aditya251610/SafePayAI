# paypal-adapter: test plan

Date: 2026-10-10. Labels: V verified, VC vendor claim, I inference/unverified. Aligned to `test-strategy.md` (sections 4, 5, 8, 11) and `sprint-plan.md`. S01-S25 IDs are the spike regression IDs from test-strategy section 5. No credentials in this doc; test fixtures are scrubbed.

## 1. Approach
- Every VERIFIED PayPal behavior is tested twice against the same assertions:
  - DOUBLE (default, CI, offline): recorded PayPal responses from the 2026-10-10 spike (scrubbed of tokens, account ids, payer PII) served by an httpx `MockTransport` / adapter-double with fault modes. Deterministic, no network.
  - LIVE (opt-in): same assertion body against the real sandbox. Marker `@live_paypal`, directory `tests_live/paypal/`, workflow `live-paypal.yml` (`workflow_dispatch` only, plus optional capped nightly), runs only with `RUN_LIVE_PAYPAL=1`; refuses to start unless host is `api-m.sandbox.paypal.com`.
- One parametrized test body per behavior: `backend` fixture = `double | live`. Divergence between double and live (double says X, live says Y) fails the live job and means the fixture must be re-recorded (fixtures carry the record date).
- Layers (test-strategy): L1 unit (ops, ticket, ledger, mapping, redaction), L2 contract (OpenAPI diff, MCP schema, double vs live), L3 integration (ephemeral Postgres schema `paypal`), L6 chaos subset.
- Tests at the adapter level assert OUR normalized envelope (api.md section 2), plus the raw PayPal fact via the double's recorded request/response.

## 2. Spike behaviors replayed (S-ID mapping)
| Test ID | Behavior | Double assertion | Live assertion (opt-in) | Spike ID(s) | Tool |
|---|---|---|---|---|---|
| PA-C01 | OAuth + expiry | token fetched once, cached; `expires_in` in the 20,000..40,000 s tolerance (I tolerance) | token fetch OK, same assertion | S01 | (client) |
| PA-C02 | Invalid token -> 401 -> refresh once -> retry same request once (same Request-Id) -> else `UPSTREAM_AUTH_FAILED` | double returns 401 then 200; and 401 twice | corrupt cached token in-process then call | S02 | (client) |
| PA-C03 | create_order | PAYER_ACTION_REQUIRED + approve link; `custom_id`=mandate_id, `invoice_id`=internal id sent | same | S03, S05 | create_order |
| PA-C04 | same-Request-Id replay returns the original | second call: same `order_id`, `replayed=true`, PayPal called once (ledger); also PayPal-level replay fixture | two raw calls with one `PayPal-Request-Id` return the same id | S04 | create_order |
| PA-C05 | capture before approval | `ORDER_NOT_APPROVED` from our pre-check; PayPal not called; PayPal's own error name recorded (U8) | observe once, record name (probe, not pass/fail) | S06 | capture_order |
| PA-C06 | capture after approval | 201 COMPLETED, `custom_id`/`invoice_id` survive | needs manual approve: pre-approved fixture mode or `@manual` Playwright (US personal buyer, V; India buyer cannot pay USD, skip documented) | S07, S23 | capture_order |
| PA-C07 | add_tracking | body has carrier `OTHER` + `carrier_name_other`, no `status`; 201; tracker id `{capture_id}-{tracking_number}`; default SHIPPED | same | S08 | add_tracking |
| PA-C08 | multiple trackers per capture | two numbers, both 201 | same | S09 | add_tracking |
| PA-C09 | tracker `status` ignored at creation | adapter never sends `status` (request-body assertion); fixture shows SHIPPED even if sent | send DELIVERED once raw; status stays SHIPPED | S10 | add_tracking |
| PA-C10 | tracker CANCELLED irreversible | adapter exposes NO cancel path (tool list + route table assertion); fixture documents 204 then `CANNOT_PATCH_CANCELLED_TRACKER` | raw probe on a FRESH capture's tracker only, never shared fixtures | S11, S12, S14 | (none exposed) |
| PA-C11 | PATCH to non-CANCELLED -> 400 | adapter has no PATCH; guard test fails the build if any code path issues PATCH to a tracker; fixture maps 400 `INVALID_PARAMETER_VALUE` -> `INVALID_PARAMETER` | raw probe on fresh tracker | S13 | (none exposed) |
| PA-C12 | partial refund | 201 COMPLETED, `refund_id`; `refund_ledger` row | same, tiny amount | S15 | refund_capture |
| PA-C13 | second partial; capture PARTIALLY_REFUNDED | second 201; get_capture status PARTIALLY_REFUNDED; derived `refundable_remaining` decremented | same | S16 | refund_capture, get_capture |
| PA-C14 | same-Request-Id refund replay returns the original | same `refund_id`, `replayed=true`, one ledger row, PayPal called once | raw replay returns original | S17 | refund_capture |
| PA-C15 | replay with DIFFERENT amount | adapter returns `IDEMPOTENCY_KEY_REUSED` (REJECTED) with NO PayPal call; separate fixture proves PayPal alone would return the original refund (hence our guard, ADR-011) | raw replay with different amount returns original amount | S18 | refund_capture |
| PA-C16 | `REFUND_AMOUNT_EXCEEDED` | 422 -> REJECTED code `REFUND_AMOUNT_EXCEEDED`; also our pre-check `AMOUNT_OVER_CEILING` / derived remaining path | over-refund | S19 | refund_capture |
| PA-C17 | `DUPLICATE_INVOICE_ID` | 422 -> REJECTED `DUPLICATE_INVOICE_ID` | reuse invoice_id | S20 | refund_capture |
| PA-C18 | concurrent identical refunds => exactly one 201 + one 409 | double fires 2 parallel; one 201, one 409 -> `IN_PROGRESS` (HTTP 202); ledger shows ONE refund; get_refund reconciles to COMPLETED; no second PayPal write | 2 parallel raw calls same Request-Id | S21 | refund_capture |
| PA-C19 | get_refund | 200 status/amount/capture link | same | S22 | get_refund |
| PA-C20 | money format | 4999 -> "49.99", property test over integer range, no float in code path | same (create order amount round-trips) | S24 | all money |
| PA-C21 | capture unknown state | timeout after capture sent -> `UNKNOWN`; get_order shows COMPLETED -> reconciled; never recapture | optional | S25 | capture_order |
- Also records, as probes (assert "recorded", not pass/fail, until baselined): refund PENDING (U1), tracker GET path (U2), webhooks (U3), real return URL (U4), get_order/get_capture shapes (U5), Request-Id retention (U6), 429 (U7), `PayPal-Request-Id` effect on tracking (U9), `paypal-debug-id` (U10).

## 3. Adapter-specific tests (no PayPal equivalent, always on the double)
| ID | Test | Source |
|---|---|---|
| PA-T01 | Startup guard: bad mode, http scheme, production host, userinfo, port, path -> exit non-zero, no secret in output; `/readyz` shows `sandbox_guard: pass` otherwise | REQ-PA-002 |
| PA-T02 | SSRF: no caller-supplied URL fetched; ID regex rejects `../`, `@`, `//`; redirects disabled | REQ-PA-003 |
| PA-T03 | Env manifest: `PAYPAL_*` only in paypal-adapter; no `LLM_API_KEY` in adapter; minter envs hold only own HMAC key | REQ-PA-001 |
| PA-T04 | Ticket negatives: forged, expired (with skew), replayed `tid`, wrong `op`, wrong `iss` vs JWT sub, amount/currency/subject/mandate/request_id mismatch -> corresponding `TICKET_*` / `AUTHORIZATION_MISMATCH`, no PayPal call | spec 5.4 |
| PA-T05 | Ticket retry of same intent (same `request_id`+`body_hash`) served from ledger, PayPal not called again | spec 5.4 step 6 |
| PA-T06 | Allowlist matrix: every (caller x tool) cell of api.md section 3 incl. LLM services and demo-inspector on money tools -> `NOT_PERMITTED`; MCP `tools/list` filtered; REST and MCP agree | REQ-PA-032 |
| PA-T07 | Kill switch: `PS_PAYPALADAPTER_MONEY_ENABLED` false/unset/garbage, DB flag set or unreadable -> `MONEY_FROZEN` on all 3 money tools, reads unaffected | REQ-PA-004, C6 |
| PA-T08 | Ledger: row IN_FLIGHT written BEFORE PayPal call (assert ordering with a spy transport); missing `request_id` -> `REQUEST_ID_REQUIRED`; local concurrent duplicate -> `IN_PROGRESS` without PayPal call; UNKNOWN stays UNKNOWN until reconciled | REQ-PA-012 |
| PA-T09 | Error mapping table (spec 7): 401, 400, 404, 409, 422 variants, 429, 5xx/timeout on write -> UNKNOWN, on read -> bounded retries then REJECTED retryable | REQ-PA-015 |
| PA-T10 | capture_order pre-checks: status not APPROVED, `custom_id` mismatch, amount mismatch -> no capture call | REQ-PA-022 |
| PA-T11 | refund_capture pre-checks: capture `custom_id` mismatch, currency, `PS_PAYPALADAPTER_REFUND_MAX_MINOR`, derived remaining | REQ-PA-023 |
| PA-T12 | Redaction canaries: client secret, access token, ticket, `token`/`PayerID`, approve-link query, payer PII, `note_to_payer` never in logs, ledger JSON, or events | REQ-PA-041 |
| PA-T13 | MCP: schema validation (`additionalProperties:false`, caps, regexes); `isError` on `ok=false`; JWT missing/wrong aud/alg none -> 401; stateless restart loses nothing | spec 11 |
| PA-T14 | Outbox: event per outbound call and per denial; at-least-once; duplicate delivery deduped on `event_id`; audit down -> retained | REQ-PA-040 |
| PA-T15 | Return URL origin allowlist: foreign origin rejected | REQ-PA-021 |
| PA-T16 | Inbound rate limit: 429 + `Retry-After`, audited; outbound concurrency cap respected | REQ-PA-042 |
| PA-T17 | Contract: OpenAPI generated == committed; MCP tool schemas generated from the same models | ADR-008 |
| PA-T18 | Fault modes (chaos subset on this PR class): double emits timeout-after-send, 409, 429, 5xx, slow response, token expiry mid-flight; assert no double effect, no blind retry | test-strategy section 3 |
| PA-T19 | Cross-service reference tests: security T1 (concurrent double-submit refund), T5 (refund not reachable by LLM services) run against adapter + resolution | test-strategy section 11 |

## 4. Opt-in live-sandbox suite
- Gate: `RUN_LIVE_PAYPAL=1`; credentials only from the `sandbox` GitHub environment / local untracked env; sandbox-host guard first.
- Quotas (our own, I): max 1 automatic run/day; max 15 sandbox orders and 15 refunds per run; counter row aborts when exceeded; tiny refund amounts (about 1-5 USD) on a dedicated sandbox merchant balance; exponential backoff and abort after 3 x 429 (PayPal limits unknown, U7).
- Cleanup: all objects tagged `custom_id=TEST-<run_id>`; never cancel trackers in shared fixtures (irreversible, V): fresh capture per tracker test; end-of-run report lists created ids and balance delta.
- Approval click is manual: pre-approved fixture mode (human approves N orders before a session via helper script) or `@manual` Playwright with the US personal sandbox buyer. Tests needing a click never run in default CI.
- Not run on forks; not part of the default `pytest`.

## 5. CI side-by-side
| Job | Trigger | Contents | Gate |
|---|---|---|---|
| `adapter-fast` | every PR touching `services/paypal-adapter/**`, `libs/**`, `contracts/**` | ruff, types, L1, double-backed PA-C01..C21 + PA-T01..T19, ephemeral Postgres schema | required |
| `adapter-chaos` | PRs touching money path (checkout, resolution, paypal-adapter, mandate) | chaos subset C1-C5, C13, C19, C20 against the adapter-double | required on those PRs |
| `secrets` | every PR + weekly | gitleaks full history | required |
| `live-paypal` | manual `workflow_dispatch` (+ optional capped nightly) | same PA-C bodies with `backend=live` + probes | advisory until S3; "green once manually" at S3 exit; green within last 48 h at S4 exit |
| Side-by-side report | after both | table: test ID, double result, live result, fixture record date, divergences | divergence = re-record fixture or file bug |
- CI never calls live PayPal or an LLM on PRs.

## 6. Sprint gates (from test-strategy section 8)
| Sprint | Required green for adapter |
|---|---|
| S1 (wk1) | lint+types; L1 core adapter; OpenAPI diff; token/401 PA-C01/C02, PA-C03/C04 (spike S01-S05 subset live once); PA-T01/T03/T08/T12 |
| S2 (wk2) | spike regression S01-S10, S24 on double (PA-C01..C09, C20); MCP allowlist + schema (PA-T06, T13); T5 refund not reachable; PA-T04/T05/T07 |
| S3 (wk3) | S11-S22, S25 on double (PA-C10..C19, C21); chaos C1-C7, C13, C19, C20; PA-T09..T11, T18; live S-suite green once manually |
| S4 (wk4) | ALL; live suite green within last 48 h; no open Sev1/Sev2 |
- Code freeze 2026-11-06; after freeze only Sev1/Sev2 fixes; final full run on 2026-11-08.

## 7. Definition of done (adapter)
- Every tool (8) has: unit tests, double-backed contract test, ledger/ticket negative tests, OpenAPI + MCP schema committed, hosted smoke pass.
- Every V behavior in spec section 2 maps to a PA-C test that passes on the double; live counterpart passed at least once (manual) by S3 exit, within 48 h by S4 exit.
- Every U item (spec 4.2) is either moved to V with a recorded fixture or left I with its fallback tested.
- Zero in each: duplicate money effect in replay/concurrency tests, PayPal write without a prior ledger row, `PAYPAL_*` outside this service, non-sandbox startup success, ticket/allowlist negative accepted, redaction canary leaked.
- gitleaks clean (full history); no secrets in logs or fixtures (fixtures scrubbed and marked `fake`).
- Docs: `docs/mcp.md` matches `tools/list`; claims list obeyed (no "official PayPal MCP", "PayPal-verified", "non-repudiable", "production-secure"; refund PENDING / webhooks / tracker GET stated as unverified).
- Reviewed by the human (deep review: money path), CI required checks green, deploy task done and smoke verified on the hosted `paypal` process.

## 8. Risks to the plan
- Live approve click prevents full automation (R6): capture proven by double in CI plus manual live run.
- Recorded doubles go stale if PayPal changes behavior: fixture record date shown in the side-by-side report; live job re-baselines.
- Sandbox flakiness or unknown rate limits (U7): live suite is advisory except at the S3/S4 exit milestones.
