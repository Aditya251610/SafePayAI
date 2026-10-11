# tracking: sprint tasks (Oct 10 - Nov 10, 2026)

Labels V/VC/I. Owner agent = AI coding agent assigned per task (names TBD by orchestrator). Each feature task has a paired test task (T) and deploy task (D). Weeks: W1 Oct 10-16, W2 Oct 17-23, W3 Oct 24-30, W4 Oct 31-Nov 10 (submit target Nov 10; deadline Nov 12 noon PT, VC). Threat-model places tracking/resolution in S3 (wk3); we start the skeleton earlier so S3 is integration, not greenfield.

## Week 1 (Oct 10-16): foundations
| id | task | pairs |
|---|---|---|
| TR-W1-1 | Scaffold `services/tracking` (FastAPI, Alembic, Dockerfile, healthz/readyz, JSON logs, internal-JWT verify via libs/common) | |
| TR-W1-2 | Schema + migration: shipments, scheduled_events, shipment_events, demo_clock, clock_jumps, detections, tick_lease, detector_runs, inbox, outbox | |
| TR-W1-3 | Injected clock abstraction (`sim_now`) + `GET /demo/clock` | |
| TR-W1-4 | Commit OpenAPI + event JSON Schemas (draft) so resolution/checkout can build against them | |
| TR-W1-T | Tests: migration up/down, clock offset unit tests, health | |
| TR-W1-D | Deploy: compose service up; `core` host mount stub; env names in `.env.example`; CI path-filtered workflow | |
| TR-W1-S | Spike (live sandbox): confirm add-tracking from our adapter stub, tracker id format, duplicate tracking number behavior (closes the I in spec 1) | |

## Week 2 (Oct 17-23): shipments + state machine
| id | task |
|---|---|
| TR-W2-1 | `order.captured` consumer (inbox dedupe) + checkout read fallback |
| TR-W2-2 | `POST/GET /shipments`, transition table, scripted outcome profiles (scheduled_events materialisation) |
| TR-W2-3 | Adapter `add_tracking` integration with persisted request id, FAILED/ADDED sync + retry; cancel endpoint (PATCH CANCELLED) |
| TR-W2-4 | Outbox relay (in-process task + `/internal/events` pull + HMAC push) |
| TR-W2-T | Tests TR-C01..C06, TR-K04, TR-A01; state-machine table tests; outbox dedupe TR-T07 |
| TR-W2-D | Deploy to hosted `core` (Profile B) with PS_TRACKING_SANDBOX_MODE true; first live add-tracking smoke |

## Week 3 (Oct 24-30): clock, poller, detector, simulator guards
| id | task |
|---|---|
| TR-W3-1 | `run_tick`: lease, apply due events with CAS, late/lost rules, detections ON CONFLICT, events with deterministic ids |
| TR-W3-2 | Triggers: in-process interval + startup catch-up, `/healthz/deep` rate-limited tick, lazy catch-up on reads, `/internal/tick`, GitHub Actions tick workflow |
| TR-W3-3 | Clock advance/reset/force with version CAS, Idempotency-Key, guards (PS_TRACKING_SANDBOX_MODE, PS_TRACKING_DEMO_CONTROLS_ENABLED, merchant role, bounds, rate limit) |
| TR-W3-4 | `demo.action_performed` audit emission (fail if outbox fails); verify endpoint + consistency block |
| TR-W3-5 | Integration with resolution: late_detected -> one case (compose) |
| TR-W3-T | Tests TR-T01..T12, TR-S01..S10, TR-K01..K03; property test tick-every-step vs one-shot |
| TR-W3-D | Deploy; configure UptimeRobot/cron-job.org/keepwarm.yml; observe cold-wake catch-up tick on hosted instance |

## Week 4 (Oct 31 - Nov 10): hardening, demo, docs
| id | task |
|---|---|
| TR-W4-1 | Demo scripting: profiles for the video (ON_TIME vs LATE vs LOST), reset, warm-up script, SIMULATED CARRIER labelling reviewed with web owner |
| TR-W4-2 | Chaos run: kill core mid-tick and mid-advance; verify no duplicate/lost detection |
| TR-W4-3 | Docs: README "Simulated carrier" section, honest-claims alignment, runbook (pingers on/off, rollback) |
| TR-W4-T | Full P0 suite both CI legs (side-by-side), 3 hosted rehearsals after cold start, gitleaks final pass |
| TR-W4-D | Freeze: no migrations after Nov 3 (I; align with release manager); rollback rehearsal once; switch pingers to review-window-only |

## Cut line and what to cut first
Must ship (above the line): REQ-TR-001..010, 012..014 (shipments, state machine, clock, tick with lease, late/lost rules, guarded + audited simulator, consistency verify, events).
Cut order if time runs short (first to go first):
1. REQ-TR-016 demo reset endpoint (use a DB reseed script instead).
2. GitHub Actions tick workflow (keep-warm ping + in-process + lazy catch-up suffice).
3. REQ-TR-015 extra profiles beyond ON_TIME/LATE/LOST (drop DELIVERED_AFTER_LATE and LOST_THEN_DELIVERED scripting; keep the anomaly check in code and tests via force).
4. REQ-TR-011 cancel + replacement shipment (keep PATCH CANCELLED only if adapter already has it).
5. Pull endpoint `/internal/events` (keep push + retry).
6. `/healthz/deep` rate-limited tick (keep plain tick triggers).
Never cut: PS_TRACKING_SANDBOX_MODE guard, audit of simulator actions, SIMULATED CARRIER labelling, double-fire protection, TR-T01/T04/T05/S01..S05.
