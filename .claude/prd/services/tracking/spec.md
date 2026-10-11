# tracking: technical spec (Python 3.12, FastAPI, SQLAlchemy 2, Alembic, httpx)

Labels V/VC/I. Schema `tracking` in the shared Postgres (ADR-004), own DB role, no cross-schema SQL. Every response carrying carrier data includes `"simulated": true` and `"carrier_label": "SIMULATED CARRIER"`.

## 1. Verified PayPal facts that shape the design (V, brief section 3)
- `POST /v2/checkout/orders/{id}/track` returns 201; tracker id = `{capture_id}-{tracking_number}`; default status SHIPPED; multiple trackers per capture allowed; `status` at creation accepted but ignored.
- PATCH `/status` works only to CANCELLED (204), irreversible (CANNOT_PATCH_CANCELLED_TRACKER after); ON_HOLD/SHIPPED/DELIVERED -> 400 INVALID_PARAMETER_VALUE.
- Therefore: PayPal tracker = "tracking added" signal only. Our `shipments.status` is truth. We store `paypal_tracker_id`, `paypal_sync` (NOT_ATTEMPTED|ADDED|FAILED|CANCELLED), `paypal_last_error`. We never read PayPal tracker status to decide anything.
- Not tested (I): behavior when the same tracking number is added twice for one capture; treat a duplicate as `ADDED` if adapter reports 4xx duplicate, else FAILED and retry (unverified).

## 2. Carrier-status state machine (our DB)
States: `LABEL_CREATED -> IN_TRANSIT -> OUT_FOR_DELIVERY -> DELIVERED` (terminal for happy path); `EXCEPTION` (carrier-reported delay/problem, non-terminal, can return to IN_TRANSIT); `LOST` (terminal-ish); `CANCELLED` (merchant cancel; terminal). "Late" is NOT a carrier state: it is a derived condition (section 6) so it can be detected idempotently.

| from | to | cause |
|---|---|---|
| (none) | LABEL_CREATED | POST /shipments |
| LABEL_CREATED | IN_TRANSIT | scheduled event or force |
| IN_TRANSIT | OUT_FOR_DELIVERY, EXCEPTION, LOST, DELIVERED | scheduled/force |
| EXCEPTION | IN_TRANSIT, LOST, DELIVERED | scheduled/force |
| OUT_FOR_DELIVERY | DELIVERED, EXCEPTION | scheduled/force |
| LOST | DELIVERED | only via force/script `DELIVERED_AFTER_LOST`; sets `anomaly=LOST_THEN_DELIVERED` |
| any non-terminal | CANCELLED | merchant cancel (+ PayPal PATCH CANCELLED best effort) |
| DELIVERED, CANCELLED | none | illegal; 409 `ILLEGAL_TRANSITION` |
Rules: transitions are validated server-side from a table; every applied transition appends `shipment_events(shipment_id, seq, from, to, source, occurred_at_sim, occurred_at_real, actor, note_code)`. `source` in {SCRIPT, FORCE, MERCHANT}. Free-text notes are not stored; only `note_code` enums (carrier notes are untrusted, threat B8).

### Tables
- `shipments(id uuid, order_id, capture_id, mandate_id, tracking_number, carrier_name, status, anomaly, outcome_profile, promised_at_sim, created_at_sim, paypal_tracker_id, paypal_sync, active bool, version int)`; unique(order_id, tracking_number).
- `scheduled_events(shipment_id, seq, due_at_sim, to_status, applied_at null, applied_by)`; PK(shipment_id, seq). The script for the shipment's `outcome_profile` is materialised at creation (deterministic, no randomness).
- `shipment_events` (append-only history above).
- `demo_clock(id=1, offset_seconds, version, updated_at)`; `clock_jumps(id, idempotency_key unique, from_sim, to_sim, actor, reason, at)`.
- `detections(shipment_id, kind, detected_at_sim, event_id, emitted bool)`; PK(shipment_id, kind), kind in {LATE, LOST}.
- `tick_lease(name pk, holder, expires_at)`; `detector_runs(id, trigger, started_at, finished_at, applied_count, detected_count, skipped_lease bool)`.
- `inbox(event_id pk)`, `outbox(seq, event_id, type, payload, status, attempts)`.
- `sim_audit(...)` is not stored locally as truth: simulator audit entries go out via outbox `demo.action_performed` to audit (section 8) plus a local copy in `shipment_events`/`clock_jumps`.

## 3. Demo-clock semantics
- `sim_now() = real_utc_now() + offset_seconds` (offset in seconds; rate is always real-time; no time dilation, I: keeps reasoning simple).
- Forward-only: `advance(delta)` requires delta > 0; no rewind. Reset (REQ-TR-016) is the only backwards move, SANDBOX only, and it also resets demo shipments' scripted events/detections for shipments tagged `demo=true` (real-sandbox orders untouched, I).
- Only tracking owns time. Other services receive `occurred_at_sim` in events, or call `GET /demo/clock`. The `promised_at_sim` is computed once at shipment creation from the order's demo protection window (config `PROTECTION_WINDOW_SOURCE=checkout`; value read from the order, not invented here).
- Advance is a single DB transaction: `UPDATE demo_clock SET offset=offset+:d, version=version+1 WHERE version=:expected` (optimistic CAS) plus a `clock_jumps` row keyed by the caller's `Idempotency-Key` (replay returns the original result). After commit it runs a synchronous tick (section 5).

## 4. Double-fire protection when the clock jumps
A jump of many days makes many scheduled events and detections "due" at once. Four layers, any one sufficient:
1. Scheduled events apply by compare-and-set: `UPDATE scheduled_events SET applied_at=:sim_now WHERE shipment_id=:s AND seq=:q AND applied_at IS NULL RETURNING`. Zero rows = someone else applied it. Events apply in `seq` order inside one transaction per shipment (`SELECT ... FOR UPDATE` on the shipment row), so a jump applies the whole due chain exactly once, in order, with `occurred_at_sim = due_at_sim` (not tick time), so history is the same whether we tick often or once.
2. Detection is `INSERT INTO detections(shipment_id, kind, ...) ON CONFLICT DO NOTHING RETURNING`; only the inserter writes the outbox event. Detections are never deleted (except demo reset, section 3).
3. `event_id = uuid5(NAMESPACE, f"{shipment_id}:{kind}")` is deterministic; consumers (resolution inbox, audit append idempotent on event_id) dedupe even if our outbox row were duplicated. resolution also has unique key (order_id, kind) (overview F4).
4. A tick holds the lease (section 5); concurrent ticks skip with `skipped_lease=true`.
Hazard handled: a jump passes both the late and lost thresholds at once. Rule: both detections are inserted (LATE then LOST) in one tx, in that order, as two distinct events; resolution's unique (order_id, kind) plus its own policy decides which case to act on (it must not refund twice; its refund idempotency is ADR-011). If the shipment is already DELIVERED at the evaluated `sim_now` after applying the chain, NO detection is created (section 6 evaluates after applying scripted events).

## 5. Poller design on a free tier (no always-on worker, no cron)
Facts: Render free web services spin down after 15 min idle and wake ~1 min (V, deployment-zero-cost); background workers/cron are not free (V); Vercel cron is once/day (V). So nothing can be assumed to run while asleep. Design principle: **correctness must not depend on tick frequency**; ticks only decide WHEN an already-determined fact is noticed.
- Tick = `run_tick(trigger)`: acquire lease; for each active, non-terminal shipment: apply due scheduled events (section 4.1), then evaluate rules (section 6) and insert detections + outbox; flush outbox; release lease. Idempotent and safe to run any number of times.
- Lease: `INSERT ... ON CONFLICT (name) DO UPDATE SET holder=:me, expires_at=now()+:ttl WHERE tick_lease.expires_at < now() RETURNING`. TTL `PS_TRACKING_TICK_LEASE_SECONDS` (value TBD, I) must exceed worst-case tick duration; a crashed holder's lease expires on its own. The DB clock (`now()`) is used for the lease, never the demo clock.
- Triggers (all call the same function):
  1. In-process interval in the `core` process: an asyncio task started in FastAPI lifespan, every `PS_TRACKING_TICK_INTERVAL_SECONDS` (TBD), cheap query (indexes on `status`, `active`). Justification: zero extra infra and zero extra hours when core is awake (deployment-zero-cost recommends in-process asyncio poller); useless while asleep, hence 2-4. It also runs one catch-up tick at startup (wake from sleep -> immediate catch-up).
  2. Keep-warm ping: UptimeRobot (5 min, V) / cron-job.org / GitHub Actions `keepwarm.yml` hit `core` `/healthz/deep`; `/healthz/deep` ALSO triggers a rate-limited tick (at most one per `PS_TRACKING_TICK_INTERVAL_SECONDS`, via lease). Keeps core awake in review windows so trigger 1 runs. Ping only the process hosting tracking (Render 750 h per workspace: only one always-on service, V; ping-all would exhaust it).
  3. Request-triggered lazy catch-up: `GET /shipments/*` and `POST /detector/run` and every call from resolution run `materialize(shipment)` (apply due events and evaluate rules for just that shipment under the row lock) before answering. So the buyer/merchant never sees stale status, and resolution re-verification (section 7) is always against current state.
  4. Secret-protected external call `POST /internal/tick` (header `X-Tick-Secret` = `INTERNAL_TICK_SECRET`, plus internal JWT when via gateway) from a GitHub Actions schedule (min cadence and delays unverified, I; scheduled workflows may be disabled after 60 days inactivity, I). Backup only.
  5. Demo-clock advance runs a synchronous tick, so the on-camera flow does not wait for any timer.
- Why not LISTEN/NOTIFY, external queue, or APScheduler persistence: they add vendors or need persistent connections (ADR-003 reasoning). Why not a separate worker: not free (V).
- Missed ticks: detection compares stored facts with sim_now, so a late tick yields the same events (with `detected_at_real` later and `occurred_at_sim` unchanged).
- Outbox relay uses the same ticks plus its own task; `GET /internal/events?after=seq` lets consumers catch up after waking.
- Outbound-traffic caution: no tight loops against PayPal; PayPal tracker calls happen only on create/cancel and retry with backoff on the tick (Render suspends on unusually high outbound traffic, V).

## 6. Late/lost rules (deterministic; thresholds are config, values TBD with PM, I)
Inputs: `promised_at_sim`, `sim_now`, status, last carrier scan time `last_event_sim`.
- LATE: status not in {DELIVERED, CANCELLED} AND `sim_now > promised_at_sim + LATE_GRACE`. (`LATE_GRACE` config `PS_TRACKING_LATE_GRACE_SECONDS`.)
- LOST: status not in {DELIVERED, CANCELLED} AND (status == LOST OR `sim_now > last_event_sim + LOST_AFTER` OR `sim_now > promised_at_sim + LOST_AFTER_PROMISE`). Both durations config; LOST_AFTER > LATE_GRACE enforced at startup (refuse to boot otherwise).
- Delivered wins: evaluated after applying scheduled events; DELIVERED at or before `sim_now` suppresses LATE/LOST regardless of `promised_at_sim` (a package delivered after the promise date but before the next tick is "late delivery", handled as an anomaly flag `DELIVERED_AFTER_PROMISE`, not a LATE detection if delivery occurred before the grace expired, I).
- EXCEPTION status does not itself trigger anything; it only pauses nothing (late rule still runs).
- Order-level: an order has an "effective shipment" = newest `active` shipment. If a newer shipment exists (replacement after cancel/loss), older cancelled shipments are ignored; detections are per shipment. If any active shipment is DELIVERED, no new detections for that order (I; matches "multiple trackers" being the same parcel list, flagged for PM).
- Events carry only enums, ids, timestamps: `{shipment_id, order_id, capture_id, mandate_id, kind, promised_at_sim, detected_at_sim, carrier_status, anomaly, simulated:true}`. No tracking-number free text beyond a masked tail; no notes.

## 7. Consistency checks
- `GET /shipments/{order_id}` returns a `consistency` block resolution consumes: `{delivered: bool, delivered_at_sim, anomaly, claim_checks:[...]}`. `GET /shipments/{order_id}/verify?claim=LOST|LATE|NOT_DELIVERED` returns `{result: CONSISTENT | CONTRADICTED | INSUFFICIENT, reason_code}` after lazy catch-up:
  - Claim LOST/NOT_DELIVERED while status DELIVERED -> CONTRADICTED `CARRIER_SAYS_DELIVERED` (resolution -> HUMAN_REVIEW; never auto-refund; buyer proof of non-delivery is out of scope).
  - Claim LATE before `promised_at_sim + LATE_GRACE` -> CONTRADICTED `NOT_YET_LATE`.
  - Claim LOST while shipment still IN_TRANSIT and not past LOST threshold -> INSUFFICIENT.
  - No shipment exists for a captured order -> INSUFFICIENT `NO_TRACKING` (merchant never shipped: policy's call, not ours).
- `LOST_THEN_DELIVERED` anomaly: emit `shipment.status_changed` with anomaly; resolution must reopen/flag HUMAN_REVIEW if a refund is already in flight (ADR-011 handles money; tracking only signals).
- Tracking number vs order: shipment's `capture_id` and `mandate_id` are copied from the `order.captured` event / checkout read, never from the client (principle P2). Reject shipment for an order not CAPTURED, or by a role other than merchant.
- Unique(order_id, tracking_number): duplicate POST with same number is idempotent (returns existing, 200) when `Idempotency-Key` or identical body; otherwise 409.
- Detector re-verification is also done by resolution (service-map: money path no; wrong signal cannot move money alone).

## 8. Simulator endpoints: guards and audit
Endpoints: `GET /demo/clock` (read, any authed role), `POST /demo/clock/advance`, `POST /demo/clock/reset`, `POST /demo/shipments/{id}/force`.
Guards, all required, evaluated in this order, fail closed:
1. `PS_TRACKING_SANDBOX_MODE` env must be exactly `true` (default false; absent = false). Else 404 (not 403, hides the surface).
2. `PS_TRACKING_DEMO_CONTROLS_ENABLED` must be `true` (second flag so a prod-like deploy with sandbox PayPal can still disable controls; the operator may turn off before judging windows if desired).
3. Valid internal JWT with `aud=tracking`, `role=merchant` (ADR-006; gateway has only buyer|merchant; threat-model "operator role" is mapped to merchant). Buyer/anonymous -> 403/401.
4. Required body `reason` (enum + optional short string, length-capped, never sent to an LLM) and header `Idempotency-Key`.
5. Per-actor rate limit at gateway plus local counter `PS_TRACKING_DEMO_MAX_ACTIONS_PER_MINUTE` (TBD).
6. Advance bounds: `delta_seconds` between 1 and `PS_TRACKING_DEMO_MAX_ADVANCE_SECONDS` (TBD); force only along allowed transitions (section 2), only on shipments the caller's merchant created or with `demo=true`.
Audit: each accepted OR rejected-after-auth attempt appends `shipment_events`/`clock_jumps` locally and emits `demo.action_performed` `{actor_sub, role, action, target, before, after, reason, idempotency_key, sandbox_mode, trace_id}` via outbox to audit (new event type; additive; conflict note C3). If the outbox insert fails the action fails (no unaudited control use). Forced events are marked `source=FORCE`; UI shows "forced by <actor>" next to the SIMULATED CARRIER badge. A forced LOST still only yields a signal; resolution's policy caps, velocity limit, human review, and the kill-switch (resolution/adapter) still apply (threat T6).

## 9. Config / env names (names only, no values)
`PS_TRACKING_DB_URL`, `PS_TRACKING_SANDBOX_MODE`, `PS_TRACKING_DEMO_CONTROLS_ENABLED`, `PS_TRACKING_DEMO_MAX_ADVANCE_SECONDS`, `PS_TRACKING_DEMO_MAX_ACTIONS_PER_MINUTE`, `PS_TRACKING_LATE_GRACE_SECONDS`, `PS_TRACKING_LOST_AFTER_SECONDS`, `PS_TRACKING_LOST_AFTER_PROMISE_SECONDS`, `PS_TRACKING_TICK_INTERVAL_SECONDS`, `PS_TRACKING_TICK_LEASE_SECONDS`, `PS_TRACKING_TICK_ENABLE_INPROCESS` (bool), `INTERNAL_TICK_SECRET`, `PS_TRACKING_INTERNAL_JWKS_URL`, `PS_TRACKING_INTERNAL_AUDIENCE` (=tracking), `PS_TRACKING_EVENT_PUSH_HMAC_KEY`, `PS_TRACKING_PAYPAL_ADAPTER_URL`, `PS_TRACKING_CHECKOUT_URL`, `PS_TRACKING_AUDIT_URL`, `PS_TRACKING_RESOLUTION_URL`, `PS_TRACKING_OUTBOX_MAX_ATTEMPTS`, `PS_TRACKING_OUTBOX_BACKOFF_BASE_SECONDS`, `PS_TRACKING_SERVICE_TRANSPORT` (http|inproc), `PS_TRACKING_LOG_LEVEL`. Secrets: `INTERNAL_TICK_SECRET`, `PS_TRACKING_EVENT_PUSH_HMAC_KEY`, `PS_TRACKING_DB_URL` live only in platform env; `.env.example` has names with empty values.

## 10. Reliability budget
- adapter `add_tracking`: timeout bounded by config, retries with backoff, same logical request id (`tracker:{capture_id}-{tracking_number}`) persisted before the call; failure leaves `paypal_sync=FAILED`, retried on ticks; never blocks shipment creation.
- Cold-start tolerance: callers (resolution, gateway) retry idempotent GETs with backoff.
- Observability: logs with trace_id, shipment_id, trigger; metrics counters (ticks, skipped_lease, detections, duplicates_suppressed, simulator_rejections) exposed on `/readyz` detail (no APM, free).

## 11. Conflicts and decisions (follow service-map.md and adr.md on conflict)
| # | conflict | resolution |
|---|---|---|
| C1 | service-map lists `POST /detector/run` "called by free external cron or scheduled loop"; deployment-zero-cost names `/internal/tick` + `INTERNAL_TICK_SECRET`. | Keep both: `/detector/run` is the gateway-routed, JWT-authed merchant/internal call; `/internal/tick` is the secret-protected external trigger. Same function. |
| C2 | threat-model says simulator behind "operator role + env flag"; ADR-006/service-map define only roles buyer\|merchant. | Operator = merchant role + PS_TRACKING_SANDBOX_MODE (+PS_TRACKING_DEMO_CONTROLS_ENABLED). Flag for gateway owner if an operator role is later added. |
| C3 | Event matrix lacks an audit event for simulator use. | Add `demo.action_performed` (additive, tracking -> audit). Needs service-map owner acknowledgement; not editing their files. |
| C4 | deployment-zero-cost recommends one Render service (profile a) while overview Profile B has 4 processes; 750 h cap allows one always-on. | tracking lives in `core`; only `core` is pinged 24/7 in review windows; edge/ai/paypal wake on demand (cold chain risk is deployment owner's, noted). |
| C5 | service-map: tracking `Consumes: order.captured` and also reads checkout. | Both: event creates an `orders_seen` row; checkout read is the authoritative fallback when the event is late/missed. |
| C6 | Overview says detector "runs on schedule/cron"; free tier has no cron. | Replaced by section 5. |
| C7 | Render free Postgres expires at 30 days (V); ADR-004 leaves host open. | Not our decision; spec assumes any Postgres; note tracking has no data older than demo needs. |
| C8 | Late/lost thresholds unspecified anywhere. | Config, values TBD with PM (I); startup refuses invalid ordering. |
