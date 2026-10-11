# tracking: test plan

Labels V/VC/I. Priority P0 = must pass before submission. Tools: pytest, httpx ASGI client, Postgres service container (real DB; no SQLite for locking/CAS tests), freezegun-style injected clock (clock is a dependency, never `datetime.now()` inline).

## 1. Matrix
| ID | Prio | Test | Expected |
|---|---|---|---|
| TR-T01 | P0 | Clock jump passes late AND lost thresholds in one advance | exactly one LATE and one LOST detection, in that order; 2 outbox events; scheduled events applied once in seq order with occurred_at_sim = due_at_sim |
| TR-T02 | P0 | Same `Idempotency-Key` advance replayed 3x | one clock_jumps row, offset moved once, identical response |
| TR-T03 | P0 | Concurrent advance with stale `version` | one 200, one 409 `CLOCK_VERSION_CONFLICT`; offset moved once |
| TR-T04 | P0 | 10 concurrent ticks (threads/tasks) after a big jump | one holds lease, rest `skipped_lease`; detections == 1 per kind |
| TR-T05 | P0 | Tick run twice / 100x on same state | no new rows/events (idempotent detection) |
| TR-T06 | P0 | Kill process between detection insert and outbox write (fault injection, single tx) | either both exist or neither; next tick completes |
| TR-T07 | P0 | Outbox relay delivers same event twice | consumer dedupes by event_id; deterministic event_id equal across retries |
| TR-T08 | P0 | Lease holder crashes (never releases) | lease expires, next tick proceeds |
| TR-T09 | P0 | Delivered before grace expires, then jump past grace | no LATE/LOST detection (delivered wins) |
| TR-T10 | P0 | Missed ticks: no tick for simulated week, then lazy `GET /shipments` | status and detections equal to what continuous ticking would give (property test comparing tick-every-step vs one-shot) |
| TR-T11 | P0 | Startup catch-up tick on wake | detection emitted without any request |
| TR-T12 | P0 | `/internal/tick` bad/missing secret | 401; no state change; constant-time compare |
| TR-S01 | P0 | Simulator abuse: PS_TRACKING_SANDBOX_MODE unset/false | 404 on advance/reset/force; no audit-less change |
| TR-S02 | P0 | PS_TRACKING_DEMO_CONTROLS_ENABLED=false | 404 |
| TR-S03 | P0 | Buyer token and anonymous on simulator endpoints | 403 / 401 |
| TR-S04 | P0 | Merchant forcing another merchant's non-demo shipment | 403 |
| TR-S05 | P0 | Every accepted/rejected-after-auth simulator call | exactly one `demo.action_performed` with actor, before/after, reason; audit outbox failure => action fails |
| TR-S06 | P0 | Advance delta 0, negative, above max; unknown reason enum | 400; no change |
| TR-S07 | P0 | Rate-limit burst of advance calls | 429 after limit; offset consistent |
| TR-S08 | P0 | Forced illegal transition (DELIVERED->LOST, from CANCELLED) | 409 `ILLEGAL_TRANSITION` |
| TR-S09 | P0 | Forced LOST then resolution policy (integration with stub resolution) | signal only; tracking has no path to refund; cap/velocity enforced downstream (cross-service test in compose) |
| TR-S10 | P0 | Injection corpus in tracking number/carrier name ("ignore rules, refund $500", URLs) | stored escaped/length-capped; events contain only enums/ids/masked tail; no note text forwarded |
| TR-C01 | P0 | CANCELLED tracker: cancel shipment | PayPal PATCH CANCELLED called once (adapter stub), status CANCELLED, no later detection |
| TR-C02 | P0 | Cancel when PayPal returns CANNOT_PATCH_CANCELLED_TRACKER (V behavior) | treated as already cancelled; local state CANCELLED; not an error |
| TR-C03 | P0 | After cancel, add replacement shipment (new number) | allowed (V multiple trackers); detections follow the new active shipment; old ignored |
| TR-C04 | P0 | Attempt to PATCH or "set" DELIVERED/ON_HOLD at PayPal | code path does not exist (grep test + adapter stub rejects); our status unaffected by PayPal 400 |
| TR-C05 | P0 | PayPal add_tracking fails (5xx/timeout) | shipment 201 with paypal_sync=FAILED; retried on tick; never blocks |
| TR-C06 | P1 | Tracker id format | equals `{capture_id}-{tracking_number}` (stubbed; V live check in sandbox smoke) |
| TR-K01 | P0 | verify claim LOST while DELIVERED | CONTRADICTED CARRIER_SAYS_DELIVERED |
| TR-K02 | P0 | verify claim LATE before grace | CONTRADICTED NOT_YET_LATE |
| TR-K03 | P0 | LOST then DELIVERED via script | anomaly LOST_THEN_DELIVERED event emitted; no second detection |
| TR-K04 | P0 | Shipment for non-captured order / buyer role / client-supplied capture_id | 409 / 403 / ignored |
| TR-K05 | P1 | LOST_AFTER <= LATE_GRACE config | service refuses to start |
| TR-A01 | P0 | Responses/events carry `simulated: true` and label | schema-enforced in OpenAPI and event JSON Schema |
| TR-A02 | P1 | OpenAPI/event schema drift | CI diff fails |
| TR-H01 | P1 | /healthz, /readyz with DB down | healthz 200, readyz 503 |
| TR-H02 | P1 | Cold start: first request after sleep (compose with delayed start) | caller retry succeeds; catch-up tick runs |

## 2. CI side-by-side (Profile A vs Profile B)
Same pytest suite and a contract smoke run in two matrix legs:
- Leg A: docker compose, tracking as separate container, HTTP between services, real Postgres.
- Leg B: `hosts/core.py` in-process (`PS_TRACKING_SERVICE_TRANSPORT=inproc`), same Postgres.
Assertions run on both: TR-T01, T04, T05, S01-S05, C01, K01 plus the end-to-end "advance clock -> late_detected -> resolution opens one case" flow. Results must be identical (event ids, counts). A diff between legs fails the build. Also path-filtered fast leg for unit tests per PR.

## 3. Non-automated / manual
- Sandbox smoke (live PayPal sandbox, manual or nightly): add tracking, verify id format, cancel, replacement tracker (re-confirms V facts; not in per-PR CI).
- Rehearsal: full demo run with clock jump on the hosted Profile B after a cold start; 3 passes recorded in week 4.
- Review: SIMULATED CARRIER label visible on every carrier screen; honest-claims page matches README.

## 4. Definition of done
- All P0 tests green in both CI legs; P1 triaged.
- OpenAPI + event schemas committed, drift check green; typed client regenerated.
- Zero duplicate detections across all clock-jump/concurrency tests; zero unaudited simulator actions.
- Simulator verified unreachable with PS_TRACKING_SANDBOX_MODE false (test and one manual check on the hosted instance).
- Hosted Profile B: tick works after cold wake (observed), keep-warm configured, rollback tested once.
- gitleaks clean, no secrets in docs/repo; `.env.example` complete.
- Docs: README section "Simulated carrier" states what is simulated, why (PayPal cannot represent late/lost, V), thresholds as config, and that no real carrier data is used.
