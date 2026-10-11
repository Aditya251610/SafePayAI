# tracking: PRD

Labels: V verified, VC vendor claim, I inference/unverified. Date 2026-10-10. Sources: 00-context-brief.md, service-map.md, adr.md, threat-model.md, deployment-zero-cost.md. No invented numbers; tunables are config with values TBD (I).

## 1. Purpose
`tracking` is the SIMULATED carrier plus the demo clock plus the late/lost detector. It is the only owner of shipment state and of "time" for the SafePayAI loop. It emits signals (`shipment.late_detected`, `shipment.lost_detected`); it never moves money. Why it exists: PayPal cannot represent late/lost/delivered (V: PATCH only to CANCELLED, irreversible; other statuses 400; creation `status` ignored), so carrier status MUST live in our DB. The PayPal tracker is only a "tracking added" signal.

## 2. Users
- Merchant (shared sandbox login, I): adds tracking, cancels a shipment.
- Demo operator (a merchant-role user while PS_TRACKING_SANDBOX_MODE is on): moves the clock, forces outcomes.
- resolution service: consumes events, reads shipment facts. Buyer: reads shipment status via gateway (read-only).

## 3. Requirements
| ID | Requirement | Priority |
|---|---|---|
| REQ-TR-001 | Merchant can add tracking for a captured order (tracking number, carrier name, promised delivery date derived server-side from order/protection window). | P0 |
| REQ-TR-002 | Creating a shipment best-effort registers a PayPal tracker via paypal-adapter `add_tracking` (carrier OTHER + carrier_name_other, V). PayPal failure must NOT block the shipment; sync status is stored and retried. | P0 |
| REQ-TR-003 | Carrier status is held in OUR DB with a defined state machine (spec section 2); every transition is an append-only `shipment_events` row. | P0 |
| REQ-TR-004 | Every UI/API surface that shows carrier data carries the label "SIMULATED CARRIER" (field `simulated: true` in every response). | P0 |
| REQ-TR-005 | Demo clock: single offset-based clock, forward-only, owned by tracking; other services get timestamps from events or ask tracking. | P0 |
| REQ-TR-006 | Clock jumps never double-fire: each scheduled carrier event applies once; each detection (shipment_id, kind) emits at most one event, forever. | P0 |
| REQ-TR-007 | Detector emits `shipment.late_detected` and `shipment.lost_detected` by deterministic rules (spec section 6). Detection is a pure function of stored facts and sim_now, so missed ticks self-heal. | P0 |
| REQ-TR-008 | Polling works on free tier with no always-on worker/cron: lease-guarded ticks triggered by (a) in-process interval in `core`, (b) keep-warm ping, (c) request-time lazy catch-up, (d) optional GitHub Actions call. | P0 |
| REQ-TR-009 | Simulator endpoints (clock advance, force status) refuse unless PS_TRACKING_SANDBOX_MODE is true AND the caller is an authenticated merchant-role user; each use writes an audit entry (actor, reason, before/after). | P0 |
| REQ-TR-010 | Consistency checks: expose facts so resolution can detect "buyer claims lost but carrier says DELIVERED", "lost then delivered", "claim before promised date" and route to HUMAN_REVIEW. | P0 |
| REQ-TR-011 | Merchant can cancel a shipment; maps to PayPal PATCH CANCELLED (V irreversible). Cancelled shipments are never late/lost-detected; a replacement shipment (new tracking number) is allowed (V: multiple trackers per capture). | P1 |
| REQ-TR-012 | Consume `order.captured` (idempotent by event_id) to know the order, capture_id, promised window. | P0 |
| REQ-TR-013 | Outbox + HTTP push + pull endpoint for events (ADR-003); deterministic event_ids for detections. | P0 |
| REQ-TR-014 | `/healthz`, `/readyz`; JSON logs with trace_id. | P0 |
| REQ-TR-015 | Scripted outcome profiles (ON_TIME, LATE, LOST, DELIVERED_AFTER_LATE) so the 3-minute demo is repeatable. | P1 |
| REQ-TR-016 | Demo reset restores clock offset and demo shipments (PS_TRACKING_SANDBOX_MODE only, audited). | P2 |

## 4. Non-goals
- No real carriers, no carrier API, no scraping, no webhooks from carriers. Never claim real carrier data (V rule in brief).
- Not PayPal's tracker status as truth. Not refund decisions. No notifications (resolution owns in-app). No address validation/geo. No multi-parcel splitting beyond "multiple shipments per order".
- No claim that the detector is a production SLA.

## 5. Metrics (measured in tests/demo, no targets invented)
| metric | how measured |
|---|---|
| Duplicate detection events per (shipment, kind) | must equal 0 in clock-jump and concurrent-tick tests |
| Detection correctness vs scripted profiles | test-plan matrix, all P0 rows pass |
| Time from clock advance to `late_detected` event emitted | recorded in demo rehearsal; no target set (unknown) |
| Simulator calls rejected when PS_TRACKING_SANDBOX_MODE off / non-merchant | 100% in tests |
| Audit entries per simulator action | exactly one |
| Demo rehearsals passing end to end | count recorded in sprint week 4 |

## 6. Risks
| risk | likelihood/impact | mitigation |
|---|---|---|
| "Looks staged": judges see a button that makes a package late and conclude the whole flow is faked | High / High | Honest labelling: SIMULATED CARRIER badge on every carrier-derived screen and response; demo-control panel visibly titled "Demo controls (sandbox)"; show the audit entry for each control use; say in video that the carrier is simulated because PayPal cannot represent late/lost (V) and real carrier feeds are out of scope; show the detector rules and that a forced status still passes policy caps and human review. Never present simulated data as real. |
| Operator abuse / public clock endpoint (threat T6, T9) | Med / High | PS_TRACKING_SANDBOX_MODE flag + merchant auth + audit + rate limit; policy caps still apply in resolution. |
| Double-fire after a big clock jump | Med / High | Scheduled-event CAS, unique detection key, deterministic event_id, lease (spec 3-5). |
| Free tier sleeps so no polling | High / Med | State-derived detection + catch-up on wake + keep-warm + request-time ticks (spec 5). |
| Render 750 h cap vs pinging several processes | Med / High | Ping only the `core` process (I; see deployment.md). |
| PayPal tracking call fails/rate | Med / Low | Signal only; stored sync status; retry; never blocks. |
| Carrier notes as injection vector | Med / Med | Notes are untrusted text, length-limited, never passed to LLM by tracking, stripped to enum codes in events. |
| Merchant cancels tracker (irreversible in PayPal) | Low / Med | Our state is independent; new shipment allowed (REQ-TR-011). |
