# web - Sprint Tasks

Labels: V verified, VC vendor claim, I inference/unverified. Aligned to sprint-plan.md phases (Gates Oct 10-11, S1 Oct 10-16, S2 Oct 17-23 ending at the DAY-14 CUT LINE Oct 23, S3 Oct 24-30, S4 Oct 31-Nov 6 ending at FEATURE FREEZE Nov 6, Freeze/submit Nov 7-10). Every feature task below is paired with a test task and a deploy task, per sprint-plan.md's standing rule ("a feature is not done until its test is in CI and it is running on the hosted Profile B environment"). Task IDs are `web`-local and map back to sprint-plan.md's `web`-touching rows (S1-10, S2-08, S2-09, S3-09, S4-01, S4-02 and others) and to REQ-WB-* in prd.md.

## Gates (Oct 10-11)
| ID | Task | Test | Deploy |
|---|---|---|---|
| WEB-G1 | Spike the Vercel-rewrite-to-Render-gateway topology (deployment.md sec 4) on a throwaway page | Manual check: cookie Set-Cookie survives the rewrite hop | n/a (spike only, feeds G1/G6 decisions in sprint-plan.md) |
| WEB-G2 | Read G5 (Agent Ready/MCP/hackathon rules) output as it affects any "no PayPal logos/SDK" or AI-disclosure copy requirement on web | Checklist item closed in docs/gates.md (owned by the gate task, web just consumes the result) | n/a |

## Sprint 1: Oct 10-16 (feature task = S1-10)
Goal (sprint-plan.md): login, sign-mandate screen, manual cart, reasons list, SANDBOX/SIMULATED banners, waking-server retry state.

| ID | Feature task | Test task | Deploy task |
|---|---|---|---|
| WEB-S1-01 | Design tokens + light/dark/system theme toggle (REQ-WB-007), persistent SANDBOX banner (REQ-WB-002), footer disclosure | Component test: theme persists, no flash; banner non-dismissible; crawl asserts banner text on every stubbed route | First Vercel deploy from main; `NEXT_PUBLIC_*` env wired per deployment.md sec 3 |
| WEB-S1-02 | Landing: persona picker (buyer ephemeral session, merchant login placeholder, judge quick path) | E2E: start session succeeds, lands on buyer home | Deploy; smoke: landing loads cold and warm |
| WEB-S1-03 | Mandate preview + sign screen (plain language + collapsed Details) against mandate api.md sec 4-5 (REQ-WB-020/021) | Component: nonce round-trip, amounts major-units-only; Playwright happy path | Deploy; vs hosted mandate service per S1 exit criteria |
| WEB-S1-04 | Manual catalog cart builder + `checks[]` reasons list rendering (REQ-WB-024), over-cap BLOCKED state with no Confirm control (REQ-WB-025) | WEB-F01 (over-cap block) Playwright test | Deploy; included in S1 hosted demo increment |
| WEB-S1-05 | Waking-up UI for cold start (REQ-WB-050), background warm-up ping on landing | WEB-F06 (cold-start) Playwright test, first pass | Deploy; verified against a real cold Render gateway per S1 exit rehearsal |
| WEB-S1-06 | Session/CSRF handling (cookie-only, CSRF in memory, REQ-WB-011), 401 -> session-ended screen (REQ-WB-012) | Security/unit test: no token in localStorage; 401 path test | Deploy |
| WEB-S1-07 | Honesty source-copy lint rule (banned-word list, REQ-WB-004) + `dangerouslySetInnerHTML` ESLint ban (REQ-WB-006) | Lint test asserting the rules fire on a planted violation, then violation removed | Wired into CI gate (lint stage) |

- Exit criteria (mirrors sprint-plan.md S1 exit): demo increment (sign mandate -> over-cap block -> confirm a valid manual cart -> PayPal handoff explainer) runs on the hosted URL 3 consecutive times; CI green; no secrets in bundle.
- End-of-sprint rehearsal (Fri Oct 16): timed run per sprint-plan.md sec 2, target <90s sign->approve->return; web's part is everything up to the PayPal handoff screen.

## Sprint 2: Oct 17-23 (feature task = S2-08, S2-09) - ends at DAY-14 CUT LINE
Goal (sprint-plan.md): intent box, agent cart panel with checks, PayPal handoff explanation, receipt, revoke; demo reset; warm-up v1.

| ID | Feature task | Test task | Deploy task |
|---|---|---|---|
| WEB-S2-01 | Intent input -> shopping-agent `/propose` BFF call (REQ-WB-023), CACHED badge rendering, manual-cart fallback on NO_MATCH/NO_PROPOSAL/AI_PAUSED | WEB-F03 (AI_PAUSED fallback) Playwright test; component test for CACHED badge exact-string rendering | Deploy; vs hosted shopping-agent |
| WEB-S2-02 | Cart confirm flow -> `approve_url`, pre-redirect explainer (REQ-WB-027), open-redirect host allowlist guard | Unit test: host allowlist blocks a mismatched URL; Playwright: explainer shows exact merchant/items/total | Deploy; `NEXT_PUBLIC_PS_WEB_PAYPAL_APPROVE_HOST_ALLOWLIST` set |
| WEB-S2-03 | Return route: strip query from address bar, call `POST /orders/return`, full status/message_code copy matrix (REQ-WB-028) | WEB-F12 (return-code matrix) Playwright test covering NOT_APPROVED, STATE_INVALID/TOKEN_MISMATCH, SIGN_IN_REQUIRED, MANDATE_REVOKED, CAPTURE_UNKNOWN | Deploy; G1 hosted re-test (sprint-plan.md Day 3) exercised through this screen |
| WEB-S2-04 | Receipt screen (REQ-WB-029): items, mandate ref, checks, "Protected until day X (demo)" + ILLUSTRATIVE tooltip, disclosures verbatim, print CSS | Snapshot test vs forbidden-claims list (test-plan.md sec 1); used directly by research Test B | Deploy; copy reviewed against banned-word list before merge |
| WEB-S2-05 | Mandate summary + Revoke action + both-effects copy (REQ-WB-022) | WEB-F02 (revoke blocks next cart) Playwright test | Deploy; Revoke button added to hosted UI |
| WEB-S2-06 | Report-a-problem screen skeleton (REQ-WB-030) - stretch if time allows, otherwise defer to S3 | Component test: char counter, neutral confirmation copy regardless of outcome | Deploy behind feature flag if shipped early |
| WEB-S2-07 | Demo reset control (REQ-WB-047), `scripts/warmup` v1 integration on landing | Test: reset requires typed confirmation; idempotent | Nightly reset workflow wired; warm-up before each recording session |

- DAY-14 CUT LINE (Thu Oct 23) - web's required contribution per sprint-plan.md sec 3: sign mandate -> cart (manual or agent) -> deterministic checks -> real PayPal order -> sandbox approve -> our return URL -> capture -> receipt, 5 consecutive clean hosted runs, one after >=12h idle (cold path uses WEB-S1-05/S2-03 waking states). **If this line is at risk, cut per section "Cut list" below - never cut the buyer mandate->cart->receipt screens themselves.**
- Exit criteria additions for web: receipt passes the forbidden-claims snapshot test; revoke demonstrably blocks a new cart on the hosted env.

## Sprint 3: Oct 24-30 (feature task = S3-09)
Goal (sprint-plan.md): merchant add-tracking, clock panel, case timeline (5 key states), offer accept, approval page, neutral human-review message, reviewer brief view.

| ID | Feature task | Test task | Deploy task |
|---|---|---|---|
| WEB-S3-01 | Merchant orders table (plain table first, AG Grid deferred to S4 per cut-order) + add-tracking form, demo clock panel (REQ-WB-040/041) | Playwright: SIMULATED CARRIER badge visible; clock advance triggers detector-visible state change | Deploy; feature-flagged if tracking contracts still moving |
| WEB-S3-02 | AI brief panel: raw text + summary + confidence side by side, policy decision shown separately (REQ-WB-042) | Component test: AI output visually separated from policy decision card | Deploy |
| WEB-S3-03 | Policy view (3 rules, ILLUSTRATIVE labels, REQ-WB-043) | Copy test: every numeric threshold carries the ILLUSTRATIVE label | Deploy |
| WEB-S3-04 | Case status tracker + timeline mapping full state machine to buyer labels (REQ-WB-034), human-review neutral status (REQ-WB-033) | WEB-F05 (injected report -> neutral status) Playwright test; copy test against banned-word list (04 Test D) | Deploy |
| WEB-S3-05 | Offer card: Approve/Decline equal weight, "software rules decided this, AI did not" (REQ-WB-031) | Component test: equal visual weight assertion; idempotent accept/decline test | Deploy |
| WEB-S3-06 | Out-of-terms approval page `/approve/[token]` (REQ-WB-032) | WEB-F07 Playwright test: replay 409, expired, wrong-session | Deploy |
| WEB-S3-07 | Report-a-problem full flow if not finished in S2 (REQ-WB-030) | WEB-F13 injection-corpus Playwright test (stub LLM) | Deploy |
| WEB-S3-08 | Human-review queue read-only view (reviewer brief) if reviewer UI lands merchant-side per prd.md sec 8 decision | Component test: no risk-reasoning leaked to buyer-adjacent screens | Deploy; cut-list item 4 candidate if behind schedule |
| WEB-S3-09 | Full honesty-label crawl wired into CI across all new S3 screens | Crawl test green across case/offer/approval/review screens | CI gate updated |

- Exit criteria additions for web: full story screens (report -> triage status -> offer -> accept -> receipt-adjacent case view) run on hosted env 5 consecutive times; injection scenes WEB-F04/F05 demonstrable live.
- If behind at Day 19 (sprint-plan.md sec 4): apply cut list items 1-6 immediately; protect the buyer-side screens (S3-04/05/06/07 core copy) over merchant polish (S3-01/02/03/08).

## Sprint 4: Oct 31-Nov 6 (feature task = S4-01, S4-02) - ends at FEATURE FREEZE
Goal (sprint-plan.md): AG Grid (time-boxed, cut-first), hardening, docs, research retest, video first cut.

| ID | Feature task | Test task | Deploy task |
|---|---|---|---|
| WEB-S4-01 | AG Grid (Community-only, time-box 2 days per sprint-plan.md S4-01): orders table, review queue, audit log with Verify-chain button + head hash (REQ-WB-040/044/045) | Playwright: filter/sort/export, keyboard nav, a11y on grids; license-feature check (Community only, R8) | Deploy; "How we use AG Grid" README section; confirm sponsor-prize mechanics before shipping |
| WEB-S4-02 | REFUNDS_FROZEN switch (merchant + buyer-safe copy, REQ-WB-046) | WEB-F08 Playwright test | Deploy |
| WEB-S4-03 | Hardening: rate-limit 429 UX, LLM-degraded-mode copy, admin-token-gated routes hidden client-side, error pages polish | Load smoke (10 parallel clicks per sprint-plan.md S4-02); 429 path test; 401 token-refresh test | Deploy; `keepwarm.yml` unaffected (web does not self-ping backend on a schedule, deployment.md sec 5) |
| WEB-S4-04 | `/about` honesty page (mirrors README, REQ-WB-005) | Content test against the exact disclosure list (prd.md REQ-WB-005) | Deploy |
| WEB-S4-05 | Full accessibility pass (section 6 of test-plan.md) across every screen | axe suite green on all screens; keyboard pass on grids | Deploy |
| WEB-S4-06 | Responsive suite pass (320px buyer, tablet-width merchant, REQ-WB-054) | Visual/responsive suite green | Deploy |
| WEB-S4-07 | Research retest copy fixes (04 section 5/9 findings) | Decisions log: finding -> change -> retest | Deploy before copy freeze Nov 5 |
| WEB-S4-08 | Judge-guide-linked "Start here" 4-step flow on landing | Playwright: a cold session can complete the 4 steps unaided | Deploy |
| WEB-S4-09 | **LATE, CUTTABLE**: Aceternity UI / WebGL hero effects on the landing page and section-transition animations only (tech-stack.md sec 3.1/3.2, spec.md sec 10 WHERE rule) - confirmed user stack decision, scoped strictly to the non-money-path landing/hook moment; zero WebGL/Aceternity imports on any buyer-core-flow or merchant-trust screen | Bundle-check: money-path route chunks (mandate sign, cart, checkout handoff, receipt, offer, audit, human-review) contain no WebGL/Aceternity code (CI build-output assertion); landing-only Lighthouse/axe pass incl. `prefers-reduced-motion` fallback and WebGL-failure fallback (tech-stack.md T1) | Deploy; feature-flag-gated if time-boxed work overruns, so it can ship disabled without blocking the S4 deploy |

- FEATURE FREEZE (Fri Nov 6): no new web features/endpoints after this point; only Sev1/Sev2 fixes, copy fixes (until Nov 5 copy freeze, then only via documented waiver), doc/video work, config hotfixes.
- AG Grid work (WEB-S4-01) starts ONLY if S3 exit criteria were met with zero open Sev1 bugs, per sprint-plan.md S4 entry criteria; otherwise it is dropped first (see cut list).
- WEB-S4-09 (Aceternity/WebGL landing) is scheduled LAST in Sprint 4, after AG Grid (WEB-S4-01) and the hardening/a11y/responsive/docs rows (WEB-S4-02 through S4-08): AG Grid carries a concrete submission stake (the single sponsor-prize mechanic, sec 9 of spec.md) and hardening/a11y/docs are acceptance-criteria-bound (test-plan.md), while the landing WebGL/Aceternity work is pure judge-appeal polish with no functional or acceptance-criteria dependency on it. It must never compete with core buyer-flow time (sprint-plan.md's standing "never cut the buyer mandate->cart->receipt screens" rule) and is explicitly the first thing dropped if S4 is tight, ahead of AG Grid - see cut order below.

## Freeze / submission phase: Nov 7-10
| ID | Task | Note |
|---|---|---|
| WEB-FR-01 | Bug-fix only pass on web (Sev1/2) | Any fix needs test + hosted smoke, no refactors (sprint-plan.md sec 6) |
| WEB-FR-02 | Final copy/label check before code freeze tag `v1.0-submission` | Full honesty crawl + gitleaks + a11y re-run |
| WEB-FR-03 | Confirm hosted demo warm and reachable logged out on submission morning | Matches sprint-plan.md Nov 10 rule |

## Day-14 cut line - what stays functional (sprint-plan.md "non-critical path" principle, prd.md non-goals)
At the Oct 23 cut line, ONLY these `web` screens must be functional end-to-end on the hosted env: mandate preview/sign -> manual or agent cart with checks/BLOCKED state -> PayPal handoff explainer -> return handling -> receipt. Everything merchant-side, AG Grid, human-review, and approval-link screens are allowed to still be stubs or feature-flagged at this point without failing the cut line.

## Cut order if time runs short (never cut the buyer mandate->cart->receipt screens)
1. Aceternity UI / WebGL landing effects (WEB-S4-09) -> fall back to a static hero (image/CSS gradient) with shadcn + light Framer Motion only; no stack-decision claim lost since the confirmed stack is still used everywhere else, just not on this one screen.
2. AG Grid (WEB-S4-01) -> fall back to plain HTML tables for orders/review/audit; no sponsor-prize claim.
3. Merchant polish beyond the minimum needed to demo the hero loop (AI brief panel detail, policy-view styling, clock panel niceties) -> keep functionally present, cut visual polish.
4. Animations/transitions (theme toggle fade, loading micro-interactions) -> cut to instant state changes; `prefers-reduced-motion` compliance is unaffected either way.
5. Reviewer brief view (WEB-S3-08) -> human reads the raw case timeline instead.
6. Out-of-terms approval link UI (WEB-S3-06) -> anything outside terms routes straight to human-review copy, no dedicated approval page.
7. Report-a-problem free text (WEB-S3-07) -> only detector-originated LATE/LOST cases are demoed.
Never cut (matches sprint-plan.md "never cut" list, web's slice of it): mandate sign screen, deterministic cart check display, real PayPal handoff + return + receipt, revoke, honesty labels and banned-word enforcement, fail-closed copy (REQ-WB-052), CI gate.

## Open items
- `services/tracking/api.md` has now been read (2026-10-10) and the add-tracking/clock/carrier BFF rows are resolved in api.md sec 7 (no longer P); remaining tracking-side gaps are listed in api.md sec 8 (demo-clock-only reset vs full admin reset UI distinction, `/shipments/{order_id}/verify` not currently surfaced to any web screen). This does not change the cut order or the Day-14 line.
- Reviewer-as-merchant-side-screen decision (prd.md sec 8) is assumed; if later decided to be a separate login, WEB-S3-08 moves under a new auth entry point, not a new screen design.
