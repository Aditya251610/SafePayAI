# web - Product Requirements (SafePayAI buyer + merchant UI)

Labels: V verified, VC vendor/secondary claim, I inference/unverified, H our own heuristic threshold, P proposed (design choice we make here, needs owner confirmation). Date 2026-10-10. Sources: context brief, service-map.md, adr.md, auth-gateway.md, 04 research plan, 05 submission plan, deployment-zero-cost.md. Where they conflict, service-map.md and adr.md win; conflicts are logged in spec.md section 17.

## 1. Purpose
- `web` is the only UI. One Next.js app (ADR-002), two route groups: buyer and merchant. It owns no data and no authorization logic; it talks only to `api-gateway` (service-map).
- It must make four things visible to a judge in under 3 minutes (05 section 4): the signed Mandate, the bounded agent and its blocked cart, a real sandbox payment, and a late order that ends in a deterministic refund with a verifiable audit trail.
- It must be honest: every simulated, cached or illustrative thing is labelled on screen, and a banned-claims list is enforced by lint and tests.

## 2. Personas
Hypotheses (I), not research findings; 04 explains grounding.

| id | persona | what they need from web | source |
|---|---|---|---|
| P1 | Cautious online buyer | Readable mandate, explicit approval click, receipt that says what is protected and until when (demo window), neutral wording when something goes wrong | 04 P1 |
| P2 | Policy-bound small merchant (single shared demo login) | Predictable policy view, a queue where odd cases wait for a human, clear reason a case went to review, override that does not pay directly | 04 P2 |
| P3 | Delegation-wary power buyer | Hard cap, allowlist, revoke, why-this-cart reasons, proof AI never decides money, audit verify | 04 P3 |
| J | Hackathon judge (PayPal developer advocate or PM) | No signup wall, "Start here" steps, loads fast when warm, graceful when cold, honesty visible, can probe audit and guardrails | 05 section 6 |
| O | Demo operator (us, recording the video, resetting between takes) | Demo clock, SIMULATED CARRIER controls, reset, scene shortcuts, no accidental real-looking claims | 05 sections 4-5 |

## 3. Success metrics
No invented numbers. "Target" = our goal, not a measured result. Research thresholds are H from 04.

| metric | target | how measured | label |
|---|---|---|---|
| Golden demo path completes on the hosted staging alias | passes on the last runs before code freeze 2026-11-09 (run count set in test-plan) | Playwright `@paypal-live` | I |
| Judge reaches first meaningful screen when API is warm | under 5 s (05 judge plan figure) | Lighthouse/Playwright timing, warm | I |
| Cold-start never shows a blank page or raw error | 100% of cold-start e2e runs show the waking UI | E2E-F05 | target |
| Honesty labels present on every required screen | 0 missing in the label matrix (test-plan section 6) | Playwright DOM assertions | target |
| Banned-word violations in source and rendered text | 0 | lint + runtime crawl | target |
| Accessibility: automated serious/critical violations on key screens | 0 | axe in Playwright | target |
| Mandate comprehension (cap, allowlist, revoke) | >=80% correct, 0 think agent can exceed cap | 04 Test A | H |
| Receipt comprehension (window, not PayPal's real window, who pays) | >=75% correct; fail if >=3 of 8 think "PayPal-backed" | 04 Test B | H |
| Escalation text read as accusatory | 0 participants | 04 Test D | H |
| LLM cart validity shown in README | actual measured value, target >=95% of 20 prompts | gateway/agent owners; web only displays source | brief |

## 4. Non-goals
- No authorization, price math, mandate evaluation, policy or refund logic in the client. UI displays server decisions; it never recomputes them (amounts shown are server values formatted for display only).
- No PayPal logos/trademarks; no PayPal JS SDK or card fields. Approval is a redirect to the sandbox approval page (V flow, brief section 3).
- No email/SMS (notifications are in-app only; service-map says email out of scope, I).
- No real carrier data, no real money, no production claims.
- No per-merchant accounts (one shared merchant login, disclosed). No real user accounts (ephemeral buyer sessions).
- No i18n, no PWA/offline mode, no native app, no third-party analytics or trackers.
- No WebAuthn signing (stretch in auth-gateway section 4.1; if built later, still not non-repudiation).
- No Channel3 integration in UI. AG Grid is used for audit log and review queue — **confirmed sponsor-prize target, D4, 00-platform-prd.md**: AG Grid is the primary build target; Render is also genuinely used as host (no extra UI work); Channel3 skipped (would require abandoning the seeded-catalog decision).
- No server-side rendering of authenticated data (avoids cookie forwarding complexity and cold-start coupling; P).

## 5. Requirements
Priority: M = must for submission, S = should, C = could (cut order in sprint-tasks.md). Acceptance criteria are testable and map to test-plan IDs.

### 5.1 Platform and honesty
| id | req | pri | acceptance |
|---|---|---|---|
| REQ-WB-001 | Next.js (TypeScript) app in `services/web`, route groups `(buyer)` and `(merchant)`, deployed to Vercel Hobby, talks only to the gateway via same-origin `/api/*` | M | Build passes; network log shows no calls to any host except the app origin and the PayPal sandbox approval page |
| REQ-WB-002 | Persistent SANDBOX banner on every page: "Sandbox only. No real money. Seeded catalog. Simulated carrier." Not dismissible | M | Label matrix |
| REQ-WB-003 | Labels SIMULATED (carrier data, demo clock effects), CACHED (any cached/golden LLM response), ILLUSTRATIVE (policy numbers, demo protection window, timeframes) appear wherever such data is shown | M | Label matrix; component tests |
| REQ-WB-004 | Banned-claims list (spec section 12) enforced: CI lint on source copy + runtime crawl of rendered text. Never "PayPal-backed". Footer: "Not affiliated with or endorsed by PayPal." | M | E2E-V02, unit lint |
| REQ-WB-005 | Honesty page `/about` mirroring README limitations: sandbox, simulated carrier, seeded catalog, 3 virtual merchants settle to one sandbox merchant, server-HMAC signing (demo-grade), demo protection window, refund is merchant-funded via PayPal refund, shared merchant login, untested items (webhooks, Disputes, PENDING refunds) | M | Content test |
| REQ-WB-006 | All server, AI, buyer and catalog text rendered as plain text (no HTML injection; `dangerouslySetInnerHTML` banned by lint) | M | Lint + injection e2e (E2E-F13) |
| REQ-WB-007 | Light/dark/system theme toggle on all pages, persisted, no flash on load | S | Component + visual test |

### 5.2 Session and landing
| id | req | pri | acceptance |
|---|---|---|---|
| REQ-WB-010 | Landing with persona picker: Buyer (creates ephemeral buyer session), Merchant (shared demo login, disclosed), "Judge quick path" with 4 numbered steps | M | E2E-01 start |
| REQ-WB-011 | Session handled by gateway cookie only; no tokens in localStorage/sessionStorage; CSRF token held in memory | M | Unit + security e2e |
| REQ-WB-012 | 401 anywhere -> "Your demo session ended" screen with one-click new session; in-progress form text preserved where safe | M | E2E-F06 |
| REQ-WB-013 | Role-based route guard in UI is convenience only; gateway enforces. Buyer cannot see merchant screens (UI hides, server denies) | M | E2E-F16 |

### 5.3 Buyer flow
| id | req | pri | acceptance |
|---|---|---|---|
| REQ-WB-020 | Mandate signing screen in plain language with exact fields (spec section 5.2): merchants, max total, intent, expiry, refund promise, revoke note; technical details (policy_version, nonce, hash, server seal) in a collapsed "Details" | M | Component + 04 Test A |
| REQ-WB-021 | Signing requires single-use challenge nonce, fresh CSRF, explicit confirm; amounts in major units with currency, integers never shown | M | Component, E2E-01 |
| REQ-WB-022 | After signing show mandate summary with visible Revoke action and semantics statement (stops future spending; protection for completed purchases stands — confirmed, D1, 00-platform-prd.md) | M | E2E-F03 |
| REQ-WB-023 | Intent input -> bounded agent proposal; shows CACHED label if source is cached; "no proposal" falls back to manual catalog cart | M | E2E-F04 |
| REQ-WB-024 | Cart proposal screen: server-priced lines, total, remaining cap, check list with plain-language reasons; advisory AI note labelled "advisory, can only tighten" | M | Component, E2E-01 |
| REQ-WB-025 | BLOCKED cart: shows blocking reason(s) in plain words, no confirm button, "Edit cart" and "Change mandate" paths; AI note cannot unblock | M | E2E-F01, F02 |
| REQ-WB-026 | NEEDS_BUYER_CONFIRMATION: extra explicit confirmation control; REJECT_WITH_REASON: treated as not purchasable with reason | M | Component |
| REQ-WB-027 | Pre-redirect explainer: "You will approve in PayPal sandbox", exact merchant/items/total; open-redirect guard validates approval URL host allowlist before navigating | M | Unit + E2E-01 |
| REQ-WB-028 | Return route handles `state`, `token`, `PayerID`: removes query from address bar immediately, calls gateway, shows waking/confirming states; never captures client-side; handles cancel, bad state, missing session, mandate revoked, CAPTURE_UNKNOWN | M | E2E-F08, F10, F15 |
| REQ-WB-029 | Receipt: items, merchant(s), total, mandate reference, check reasons, PayPal order/capture ids, "Protected until day X (demo)" with ILLUSTRATIVE tooltip, "refund is merchant-funded via PayPal refund", SIMULATED CARRIER label, next steps, print-friendly | M | Component, label matrix |
| REQ-WB-030 | Report a problem: free text with counter, order picker; submit shows neutral confirmation; text rendered back as untrusted | M | E2E-F13 |
| REQ-WB-031 | Offer card: exact refund amount, why it applies (inside signed terms), who funds, expiry, "software rules decided this, AI did not", Approve and Decline equally reachable, idempotent | M | E2E-01 |
| REQ-WB-032 | Out-of-terms approval link page `/approve/[token]`: requires same buyer session, shows exact proposal terms from server, fresh confirm, handles replay (409), expired, revoked, wrong session | M | E2E-F09 |
| REQ-WB-033 | Neutral human-review status screen using 04 wording; never exposes risk reasoning; says a person decides; lets buyer add details | M | Copy test, E2E-F12 |
| REQ-WB-034 | Case status tracker maps the 12 states to buyer-friendly labels with a timeline | M | Component |
| REQ-WB-035 | History: mandates, orders, cases for this buyer with links | S | Component |

### 5.4 Merchant flow
| id | req | pri | acceptance |
|---|---|---|---|
| REQ-WB-040 | Orders table (AG Grid): order, buyer id (ephemeral), items, total, state, tracking, carrier status badge SIMULATED CARRIER, promise date | M | E2E-01 |
| REQ-WB-041 | Per-row add tracking, force carrier status (SIMULATED), shared demo clock panel (current demo day, advance by N days, run detector) with SIMULATED label | M | E2E-01 |
| REQ-WB-042 | AI brief panel: raw buyer text beside AI summary, category, confidence, "advisory; AI does not decide refunds"; draft messages marked "draft, not sent"; policy decision shown separately from the AI output | M | Component |
| REQ-WB-043 | Policy view: three rules with ILLUSTRATIVE label, plus per-case rule results | M | Component |
| REQ-WB-044 | Human-review queue (AG Grid) with detail pane and Override, which creates a NEW offer needing buyer approval; UI states no money moves until buyer approves | M | E2E-F12 |
| REQ-WB-045 | Audit log (AG Grid) with Verify chain button, result banner, head hash with copy, chain epoch | M | E2E-01, F14 |
| REQ-WB-046 | REFUNDS_FROZEN switch with confirm; frozen state visible on merchant and as neutral note on buyer case ("refunds are paused for review") | S | E2E-F11 |
| REQ-WB-047 | Demo reset control with typed confirmation; only shown in demo mode | M | E2E-S01 |

### 5.5 Resilience, accessibility, delivery
| id | req | pri | acceptance |
|---|---|---|---|
| REQ-WB-050 | Graceful "waking up" UI for cold start; background warm-up on landing; no blank page; retry with backoff for idempotent calls; offline-video banner after give-up | M | E2E-F05 |
| REQ-WB-051 | Every mutating call carries `Idempotency-Key` and CSRF; double-click safe | M | E2E-F17 |
| REQ-WB-052 | Fail-closed copy: if the gateway cannot confirm rules, UI says nothing was bought/refunded | M | Copy test |
| REQ-WB-053 | Accessibility basics (spec section 13): keyboard, focus, labels, contrast, 200% zoom, reduced motion; automated axe checks | M | A11y suite |
| REQ-WB-054 | Responsive minimum: buyer flow works from 320 px; merchant views usable from tablet width | M | Visual suite |
| REQ-WB-055 | Vercel zero-cost deploy with preview deploys, env names only in repo, documented rollback | M | deployment.md checklist |
| REQ-WB-056 | CI: lint, typecheck, unit, contract check, build, e2e against compose stack, a11y; path-filtered, side by side with backend workflows | M | test-plan section 9 |
| REQ-WB-057 | Demo mode (`NEXT_PUBLIC_PS_WEB_DEMO_MODE`): guided steps, scene shortcuts for guardrail demos, pre-seeded late order link; fakes no outcomes | S | Component |
| REQ-WB-058 | Generated API types from `contracts/openapi/api-gateway.json`; runtime response validation (zod) with graceful unknown-field tolerance | S | Contract test |

## 6. Constraints from other docs (do not violate)
- Gateway strips client identity headers and derives identity from the cookie (auth-gateway 2.1); web never sends role/user ids as authority.
- Server derives merchant, amount, currency, capture_id; web sends SKUs, quantities, intent, and ids only (brief principle).
- Return URL must come from env/gateway, not hard-coded (deployment-zero-cost section 5).
- Vercel Hobby limits relevant here (V, deployment-zero-cost): 100 deployments/day, 120 s proxied timeout, runtime logs kept 1 h, cron once per day.

## 7. Risks
| # | risk | impact | mitigation | label |
|---|---|---|---|---|
| R1 | Cold start of Render gateway (about 1 min, V) on first judge click | Looks broken | Waking UI, early warm-up call, Profile B, video fallback banner | V/I |
| R2 | Cookie not first-party if web (vercel.app) calls gateway (onrender.com) directly | Session breaks, SameSite=Lax | Same-origin `/api/*` via Vercel rewrite (auth-gateway 2.3 preferred option); verify Set-Cookie passes through in week 1 | I |
| R3 | PayPal return URL into our own app untested (brief gap) | Demo cannot finish | Spike in week 1 on the hosted alias; return route designed for retries and state binding | V gap |
| R4 | Real approval click cannot be automated reliably | Flaky CI | `@paypal-live` tests nightly/manual; PR CI stops at handoff and tests return-error paths | I |
| R5 | Gateway BFF endpoints in api.md are not yet in service-map | Blocked screens | Gap list in api.md; MSW mocks from contract in dev only (never in production build) | P |
| R6 | Copy drifts into banned claims | Dishonest claim in video | Lint, crawl test, copy table single source, reviewer checklist | target |
| R7 | LLM 429 during judge bursts | Agent/triage degrade | UI shows degraded modes (manual cart, human review, CACHED) clearly | V (deployment doc) |
| R8 | AG Grid license/feature confusion (row grouping etc. are enterprise, I) | Sponsor-prize use looks thin or licence breach | Use Community features only (sort, filter, pinning, custom cell renderers, CSV export, master/detail by own pane); confirm licence terms in week 1 | I |
| R9 | Preview deploys have different origins | Gateway Origin/CSRF checks and return URLs fail | Previews run `API_MODE=mock` with visible banner, or gateway allowlist pattern (decision in deployment.md) | I |
| R10 | Accessibility regressions in data grids | Fails basics | Keyboard test on grids, axe, row detail outside the grid | I |
| R11 | Judges share one merchant session and reset each other's data | Confusing state | Ephemeral buyers isolate buyers; reset only affects demo data and shows epoch; merchant sees data only for current epoch | I |
| R12 | Free-tier Vercel changes | Deploy surprises | Re-check limits 2026-11-01 (deployment-zero-cost) | I |

## 8. Open questions
- Exact BFF endpoints, field names, error code names (api.md is a proposal; gateway owner confirms).
- Merchant persona entry: one-click vs published demo password (ADR-006 vs frictionless judge access).
- Reviewer role: separate actor (auth-gateway) or merchant-side screen (service-map)? web builds it as merchant-side with a self-asserted display name field.
- Revoke semantics for already-captured orders (overview F5 vs auth-gateway section 6, both I).
- Whether LLM golden/cached mode exists and how the response flags it.
- ~~Which single sponsor prize is chosen~~ — resolved, see D4: AG Grid.
