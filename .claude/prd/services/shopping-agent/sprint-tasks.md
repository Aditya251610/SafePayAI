# shopping-agent: sprint tasks

Labels V/VC/I. Dates and cut/freeze lines follow `sprint-plan.md` (PRD root) exactly: sprint window Oct 10-Nov 10 2026; DAY-14 CUT LINE = Thu Oct 23 (evening); FEATURE FREEZE = Fri Nov 6 (Day 28); submit Nov 10. Task IDs below are service-local (`SA-Wn-xx`); they map to the PRD-root IDs (`S1-12`, `S2-04`, `S2-05`) where one exists, noted inline. Every feature task is paired with a test task and a deploy task per the project rule.

## Week 1 (Oct 10-16, Days 1-7) — eval harness only (= sprint-plan S1-12)

| ID | Feature task | Test task | Deploy task |
|---|---|---|---|
| SA-W1-01 | Scaffold `services/shopping-agent/` (FastAPI app, `agent` schema skeleton, Alembic, pydantic models from spec.md sec 3) | Unit tests U1-U5 (schema `extra=forbid`, SKU/qty bounds, dedupe) green in CI | Dockerfile builds; mounted (stub router only, no live call) in `hosts/ai.py` |
| SA-W1-02 (= S1-12) | 20-prompt cart eval set committed (`evals/cart_20.jsonl`, placeholders until catalog seed lands), provider switch scaffold (Gemini/Groq config, no real traffic yet), injection prompts included | G4 report committed: schema-valid %, failures, model id, date (sprint-plan gate) | LLM key present only in `ai` process env; no billing account linked to the Gemini project; hard monthly budget noted in README |
| SA-W1-03 | Form-driven fallback matcher (spec.md sec 7), pure deterministic function, no LLM dependency | U10 (determinism), F6 (same 20 prompts through form matcher, zero dead ends) | Deploy behind the same router; reachable even with `LLM_ENABLED=false` from day 1 |
| SA-W1-04 | Internal JWT audience check (`aud=shopping-agent`), deny-by-default, `/healthz`/`/readyz` | Deny-by-default tests (no token, wrong aud, expired) — shared `libs/common` test suite (S1-03) | `/healthz`,`/readyz` live on hosted Profile B `ai` process |

Exit (Week 1): eval harness runs end-to-end against a stub/mock catalog (real catalog not seeded until S1-06 lands elsewhere); form fallback works standalone; no live cart proposal UI yet (web/checkout wiring is Week 2).

## Week 2 (Oct 17-23, Days 8-14) — ends at DAY-14 CUT LINE (= sprint-plan S2-04, S2-05)

| ID | Feature task | Test task | Deploy task |
|---|---|---|---|
| SA-W2-01 (= S2-04) | `POST /propose` live: schema validation, 1 retry (5xx/timeout only), manual-cart/form fallback wired; untrusted catalog text handled as delimited data (spec.md sec 4) | 20-prompt suite runs nightly in CI against live LLM + deterministic mock-LLM unit tests (U1-U12); injection prompts (17-20) -> still schema-valid or `NO_PROPOSAL`; report actual % (not assumed) | Deploy in `ai` process; 429 backoff + provider fallback test (Gemini -> Groq, S6); cost guard (daily cap) enforced by `llm-gateway` |
| SA-W2-02 (= S2-05) | `POST /intent-fit`: `PASS \| NEEDS_BUYER_CONFIRMATION \| REJECT_WITH_REASON`, tighten-only, callable only by `svc:checkout`, only after checkout's hard checks pass | U8, U9, S5 (AI PASS cannot override a hard block — property test shared with mandate T4); timeout/error -> `NEEDS_BUYER_CONFIRMATION`; garbage/schema-fail output -> restrictive default | Deploy; advisory label (`advisory:true`) shown in UI via checkout's response; caller-allowlist test (C3) |
| SA-W2-03 | Caching: `llm-gateway` cache key wiring (spec.md sec 8), pre-warm script for scripted demo inputs, `source`/`badge` fields on every response | U11 (cache key construction); snapshot test that a cached response always carries the badge text and is never relabeled live | Deploy; `scripts/warmup.sh` extended to pre-warm scripted intents before each recording session |
| SA-W2-04 | Outbox: `cart.proposed` event emission (spec.md sec 12/api.md sec 8) | At-least-once dedupe by `event_id`; order of `mandate.signed -> cart.proposed -> cart.checked -> order.created` in the audit chain (shared with S2-06) | Deploy; wired into the same outbox relay as mandate/checkout/adapter (S2-06) |
| SA-W2-05 | `/propose`, `/intent-fit` end-to-end against real `catalog`/`mandate` (no longer mocked) | Contract tests C2-C5; IDOR check: buyer cannot propose against another buyer's mandate (404, shared with checkout's IDOR suite) | Deploy; hosted smoke test included in the S2 exit demo rehearsal |

### DAY-14 CUT LINE (Thu Oct 23, evening) — this service's contribution to the pass criteria
- Must be true for the overall cut line (sprint-plan.md sec 3) to pass: agent cart proposal works on the hosted demo OR manual cart works identically well — the cut line does NOT require the LLM path to be live, only that SOME cart path (agent or manual/form) completes the full sign -> cart -> order -> capture -> receipt flow 5 consecutive times, including one cold-start run.
- **Explicit cut-first rule (locked):** if the LLM path for shopping-agent is unstable, flaky, or behind schedule at the cut line, the FIRST thing cut is live agent chat (`/propose` live mode) — not the mandate, not checkout, not PayPal capture. The service falls back to the deterministic form/canned-intent path (spec.md sec 7), which is built in Week 1 (SA-W1-03) specifically so it is ready as the fallback before the cut line is even reached.
- Order of what gets cut, if needed, ahead of the cut line or immediately after (mirrors sprint-plan.md sec 7 cut list items 9-10, applied to this service specifically):
  1. **Cut first: live agent chat / `/propose` in `mode="intent"`.** Fallback: canned/form intent only (`mode="form"`, spec.md sec 7) — buyer picks category + budget + quantity, deterministic matcher proposes lines. Zero LLM calls. Demo narration shifts to "buyer builds the cart; the Mandate still blocks it if over cap."
  2. **Cut second: `/intent-fit` advisory check.** Fallback: hard checks only (mandate `/evaluate`); no advisory tightening step shown in the UI. This matches cut list item 9 in sprint-plan.md.
  3. **Never cut:** the deterministic re-pricing handoff to `checkout`/`mandate` (spec.md sec 6) — this is not an agent feature, it is the money-safety boundary, and removing it is not on this service's cut list at all.
- If the cut line fails for reasons outside this service (per sprint-plan.md sec 3): "freeze AI features (S2-04/05 revert to manual cart)" applies verbatim — SA-W2-01 and SA-W2-02 are reverted to their Week 1 fallback state (SA-W1-03) and no further agent work happens until the failing path (elsewhere in the system) is fixed.
- Exit criteria for this service at the cut line: form fallback (SA-W1-03) proven live on hosted Profile B; `cart.proposed` event present in the audit chain when the agent path IS used; G4 eval re-run result recorded (actual %, not assumed); CI green.

## Week 3 (Oct 24-30, Days 15-21) — hardening, no new agent features planned

| ID | Feature task | Test task | Deploy task |
|---|---|---|---|
| SA-W3-01 | Eval re-run after any catalog/model change; baseline comparison (`evals/baseline.json`) | E2 (regression rule): full 20+12 set re-run, not spot checks | Recorded results committed; promotion (if any) is a human-reviewed config change, never auto |
| SA-W3-02 | Injection corpus hardening: confirm all 4 injection cases (17-20) plus the shared `fixtures/injection/*.jsonl` corpus entries pass in CI (stub) and are recorded (live) | S1-S4 green; live-LLM confirmation recorded with model id/date | No deploy change expected; config-only if a prompt tweak is needed |
| SA-W3-03 | Observability: "AI trace" panel data (trace_id/span_id chain) verified end-to-end for a `/propose` call through to the audit entry | Manual verification against the reviewer UI panel (shared with triage-ai/agent-and-mcp-design sec 5) | n/a (read-only panel lives in `web`/`audit`) |

This service has no critical-path items in Week 3 (sprint-plan.md critical path graph runs tracking/resolution/refund in this window); work here is hardening and research-copy support only.

## Week 4 (Oct 31-Nov 10, Days 22-32) — hardening, freeze, submit

| ID | Feature task | Test task | Deploy task |
|---|---|---|---|
| SA-W4-01 | Full `LLM_ENABLED=false` end-to-end soak (F5): protect -> cart (form) -> order -> capture -> receipt | F5 passes on hosted Profile B, not just locally; run as part of the project-wide soak test before feature freeze | No deploy change; this is a verification task |
| SA-W4-02 | Copy/UI pass on "AI assist paused (free-tier limit) - using form mode" and cache badge text, per research findings (doc 04) | Snapshot test against forbidden-claims list (no "injection-proof", no "PayPal-backed") shared with checkout's receipt test | Copy fixes deployed by the Nov 5 copy freeze (sprint-plan.md S4) |
| SA-W4-03 | Final eval run + README update: actual Gemini free RPM/RPD recorded, model ids and dates pinned, model freeze Nov 5 (llm-cost-and-latency.md sec 6) | E1-E4 final pass, baseline committed as the frozen reference | Deploy frozen; no model/prompt change allowed after Nov 6 (feature freeze) except sev-1/sev-2 fixes |
| SA-W4-04 | gitleaks full-history re-scan, secrets rotation check (this service never held PayPal creds, so rotation is limited to `PS_SHOPPINGAGENT_GEMINI_API_KEY`/`PS_SHOPPINGAGENT_GROQ_API_KEY` if ever exposed) | S7/T13 clean | n/a |

### FEATURE FREEZE (Fri Nov 6, Day 28)
- No new endpoints, no schema changes, no model swaps for this service after this date. Allowed: sev-1/sev-2 bug fixes, copy fixes already scheduled for Nov 5, config hotfixes (e.g. adjusting a rate-limit number), doc/video work.
- If AG Grid or any other stretch item elsewhere in the system is dropped per sprint-plan.md sec 7 cut list, this service is unaffected (it has no AG Grid dependency).

## What to cut first (summary, cross-referenced to sprint-plan.md sec 7 cut list)
Within this service, in order:
1. Live agent chat (`/propose` intent mode) — first cut, per the explicit rule above and matching cut list item 10 ("LLM shopping agent -> manual cart + preset suggestions").
2. Intent-fit advisory check — second cut, matching cut list item 9 ("Intent-fit advisory -> Hard checks only").
3. Caching/pre-warm niceties (badge polish, pinned demo inputs beyond the minimum needed to not dead-end) — cut before touching the form fallback itself, since the form fallback is the thing everything else degrades into.
Never cut (not on this service's list at all, and not on the project's never-cut list either): the deterministic handoff to `checkout`/`mandate` re-pricing and hard checks — this is a safety boundary, not an agent feature.

## Conflicts / open items noted (not resolved here; see spec.md sec 14)
- Exact day the catalog seed lands determines when SA-W1-02's placeholder SKUs (`SKU-RUN-1` etc.) are replaced with real ones in `evals/cart_20.jsonl` — tracked against catalog's own sprint tasks (S1-06), not duplicated here.
- `llm_cache`/`llm_calls` schema ownership (spec.md C2) affects whether SA-W2-03's caching task needs its own migration or shares one with `triage-ai`; flagged for the owner decision noted in spec.md, not blocking Week 2 work (the cache can start schema-local and move later).
