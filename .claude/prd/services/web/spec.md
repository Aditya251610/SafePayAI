# web - Technical Spec and UX Architecture (SafePayAI)

Labels: V verified, VC vendor claim, I inference/unverified. Source of truth is `prd.md`; service-map.md and adr.md win on conflicts (logged in section 17). No tech-stack.md exists yet at write time; frontend framework/hosting is taken from ADR-002/ADR-009 (Next.js + TypeScript, pnpm, Vercel) and REQ-WB-001/055. If tech-stack.md appears later and disagrees, tech-stack.md wins; re-sync this file.

## 1. Information architecture

```
/                          landing: persona picker (Buyer / Merchant / Judge quick path)
(buyer)/
  /start                   ephemeral session creation
  /mandate/new             preview -> sign (plain language + collapsed Details)
  /mandate/[id]            summary, Revoke, protection terms
  /intent                  intent text box -> agent proposal (or manual catalog)
  /cart/[id]               proposal: lines, total, remaining cap, checks, BLOCKED state
  /checkout/handoff/[id]   pre-redirect explainer -> PayPal sandbox approve
  /orders/return           PayPal return handler (state, token, PayerID)
  /orders/[id]/receipt     receipt: protected-until, disclosures, print view
  /cases/new               report a problem (free text)
  /cases/[id]              status tracker (buyer-friendly labels), offer card, appeal
  /approve/[token]         out-of-terms approval link
  /history                 mandates, orders, cases list
  /about                   honesty page (mirrors README)
(merchant)/
  /orders                  AG Grid: orders + SIMULATED CARRIER controls + demo clock
  /orders/[id]             AI brief panel (confidence + raw buyer text), tracking form
  /policy                  read-only 3-rule policy view
  /review                  AG Grid: human-review queue + override
  /audit                   AG Grid: audit log + Verify-chain + head hash
  /controls                REFUNDS_FROZEN switch, demo reset
_shared
  401 screen, waking-up screen, theme toggle, SANDBOX banner (persistent, REQ-WB-002)
```
Route guard is UI convenience only (REQ-WB-013); gateway is authoritative.

## 2. Screens and states - buyer

### 2.1 Mandate signing (REQ-WB-020/021)
- Plain-language fields only, matching mandate `preview` response: merchants (display_name list), max total (major units + currency), intent text, expiry, protection promise (kinds_covered, max_refund_minor as major units, deliver_by_days), revoke note ("stops future spending; a purchase you already completed keeps its protection - P, pending confirmation, see section 17").
- Collapsed "Details": `policy_version`, `nonce` (shown once, from `preview`), `screen_text_hash`, "server attests an authenticated session saw these terms" (demo-grade, not a signature) per auth-gateway sec 4.1.
- Flow: GET/POST `preview` -> render -> Sign button requires fresh CSRF + the nonce from preview -> POST `/mandates`. Single-use nonce expires; expired nonce re-requests preview automatically with a visible "terms refreshed" note.
- States: draft, previewing, signing (disabled button, spinner), signed (redirect to summary), error (`NONCE_INVALID`, `SCREEN_TEXT_MISMATCH` -> re-preview; `TERMS_OUT_OF_BOUNDS`/`UNSUPPORTED_CURRENCY` -> inline field errors).
- Integers never shown; all amounts formatted from `*_minor` to major units client-side for display only (no math).

### 2.2 Mandate summary (REQ-WB-022)
- Status, remaining cap, visible Revoke button. Revoke confirmation modal states both effects: stops future agent/manual purchases; already-captured protection is not reversed (per auth-gateway sec 6; confirmed, D1, 00-platform-prd.md — this doc has no section 17, that cross-reference was stale).
- Revoke response fields shown: `released_reservations`, `message_code` mapped to buyer copy (e.g. `FUTURE_PURCHASES_STOPPED` -> "You won't be able to start new purchases with this mandate.").

### 2.3 Intent input and cart proposal (REQ-WB-023/024)
- Intent textbox (<=500 chars, matches `PS_SHOPPINGAGENT_INTENT_MAX_CHARS`) -> calls BFF which proxies `shopping-agent POST /propose`.
- `source: "cached"` renders the CACHED badge text verbatim from the response (`badge` field) - never invented wording.
- `status: "NO_MATCH" | "NO_PROPOSAL" | "AI_PAUSED"` -> falls back to manual catalog cart builder; copy: "The assistant couldn't build a cart. Pick items yourself."
- Accepted lines are sent as `{sku, qty}[]` + `mandate_id` to `checkout POST /carts` only - proposal fields (rationale, confidence, model) are never sent downstream (per shopping-agent api.md sec 4).
- Cart screen renders `checks[]` from `checkout POST /carts` response as plain-language rows: PASS (grey check), BLOCK (red, with `reason_code` mapped to copy table sec 10), TIGHTEN/advisory intent_fit (blue, labelled "advisory, can only tighten, cannot clear a block").
- Remaining cap, total, per-line unit price - all formatted from server integers, no client math beyond minor->major display conversion.

### 2.4 BLOCKED cart (REQ-WB-025)
- `status: "BLOCKED"` (from `checks` containing a BLOCK result, see checkout api.md sec 3): no Confirm button rendered at all (not just disabled - absent, so no client-side bypass surface).
- Shows every BLOCK reason in plain words (copy table sec 10), "Edit cart" (back to manual builder) and "Change mandate" (to `/mandate/new` or existing mandate list) links.
- AI advisory note, if present, is rendered but explicitly cannot remove the block banner.

### 2.5 NEEDS_BUYER_CONFIRMATION / REJECT_WITH_REASON (REQ-WB-026)
- `NEEDS_CONFIRMATION` cart status: extra explicit checkbox/button "I understand and want to continue" required before Confirm is enabled, mapped to `confirm_intent_fit: true` in `POST /carts/{id}/confirm`.
- `REJECT_WITH_REASON` (intent_fit verdict) is treated as advisory tightening only; if it appears alongside a hard block it never substitutes as the reason shown - hard block reasons always take visual priority.

### 2.6 Pre-redirect explainer and PayPal handoff (REQ-WB-027)
- Exact merchant names, item list, total (major units) from `confirm` response before navigating to `approve_url`.
- Open-redirect guard: `approve_url` host must match an allowlist (env, sec 14) before `window.location` navigation; mismatch -> error screen, no navigation, logged.
- Copy: "You will approve this purchase on PayPal's sandbox site. No real money moves."

### 2.7 Return handling (REQ-WB-028)
- Route receives `state`, `token`, `PayerID` from PayPal; immediately `history.replaceState` to strip the query string from the address bar (no-referrer already set server-side per auth-gateway sec 2.3).
- Calls BFF `POST /orders/return` with the three values; never captures client-side (per checkout api.md sec 5 - capture is server-only).
- States: waking (if gateway cold), confirming (spinner), success (-> receipt), and explicit copy per response code: `NOT_APPROVED` ("Not approved yet - click Approve again"), `STATE_INVALID`/`TOKEN_MISMATCH` ("This link looks wrong. Start checkout again."), `SIGN_IN_REQUIRED` ("Sign back in to finish - nothing was charged"), `MANDATE_REVOKED`/`CANCELLED_REVOKED` ("Your mandate was revoked before this could complete"), `CAPTURE_UNKNOWN`/`PAYPAL_UNAVAILABLE`/503 ("We can't confirm yet - checking... ") with poll/retry on `GET /orders/{id}` (never "payment failed" when the true state is unknown - fail-closed copy, REQ-WB-052).
- Cancel path (`/orders/cancel`) shows a neutral "Checkout cancelled, nothing was charged" screen.

### 2.8 Receipt (REQ-WB-029)
- Fields exactly from `GET /orders/{id}/receipt` (checkout api.md sec 8): items, merchant(s), total, mandate reference (`mandate.mandate_id`/hash), `checks[]` reasons, PayPal `order_id`/`capture_id`, "Protected until day X (demo)" built from `protection.protected_until_day` with an ILLUSTRATIVE tooltip ("demo clock day, not a calendar date, not PayPal's own window"), "refund is merchant-funded via PayPal refund" (from `disclosures[]`, rendered verbatim, never paraphrased into a stronger claim), SIMULATED CARRIER label where carrier facts would appear, next steps (report a problem, view case), print-friendly CSS (`@media print`).
- `receipt.disclosures[]` array is rendered as a bullet list, not summarized - the server owns the exact wording.

### 2.9 Report a problem (REQ-WB-030)
- Free text with live character counter (server cap from `PS_RESOLUTION_CASE_REPORT_MAX_CHARS`, sec 14), order picker (from buyer's own order list only).
- On submit: neutral confirmation only ("We've logged this and are looking into it") regardless of triage outcome - UI never shows the triage category or confidence to the buyer.
- The buyer's own submitted text is rendered back anywhere it reappears (e.g. case detail) as plain text via React's default escaping; `dangerouslySetInnerHTML` is banned (lint rule, REQ-WB-006).

### 2.10 Offer card (REQ-WB-031)
- Exact refund amount (major units), "why it applies" from `decision.reasons[]`/offer summary (inside signed terms language), who funds ("merchant, via PayPal refund"), expiry countdown, "Software rules decided this; AI did not. AI only read your message and summarized it.", Approve and Decline rendered as equal-weight buttons (same size, same visual priority, no default focus bias).
- Idempotent accept/decline: a second click or a stale replay shows the current resolved state instead of erroring (per resolution api.md sec 3.5/3.6).

### 2.11 Out-of-terms approval link (REQ-WB-032)
- `GET /approvals/{token}` renders exact terms server-side before any state change; requires the same buyer session (mismatch -> 404, shown as "This link isn't for your session").
- Fresh CSRF nonce required on confirm; handles `APPROVAL_REPLAY` (409 -> "Already used"), `APPROVAL_EXPIRED` (-> "Expired, your case moved to human review"), `APPROVAL_REVOKED`, wrong-session (404-style generic message, no existence oracle).

### 2.12 Human-review status (REQ-WB-033)
- Neutral wording only (sourced from 04 Test D wording list and resolution's own reason text, which already passes the banned-word gate per resolution api.md sec 1): "A person is reviewing your case. Your coverage stays active." Never shows risk reasoning, confidence, or words like "flagged"/"suspicious"/"fraud"/"abuse".
- Buyer can add details via the appeal endpoint (`POST /cases/{id}/appeal`).

### 2.13 Case status tracker (REQ-WB-034)
- Maps resolution's full state machine to buyer-friendly labels and a timeline component built from `timeline[]` in `GET /cases/{id}`. Exact state->label mapping is a copy-table entry (sec 10), not invented per-screen.

### 2.14 History (REQ-WB-035)
- Lists mandates, orders, cases for the current buyer with deep links; paginated via each service's own cursor/limit.

## 3. Screens and states - merchant

### 3.1 Orders table (REQ-WB-040/041)
- AG Grid (Community features only - sort, filter, pinning, custom cell renderers, CSV export; no row grouping/enterprise features, R8/sec 12): order id, buyer id (ephemeral, shown as opaque id, never implying real identity), items, total, state, tracking status, "SIMULATED CARRIER" badge cell renderer, promise date.
- Per-row actions: add tracking (calls checkout/tracking via BFF), force carrier status (SIMULATED, explicit confirm dialog restating "this does not reflect a real carrier").
- Shared demo clock panel: current demo day, "advance by N days" input, "run detector" button - all labelled SIMULATED; visible only when `NEXT_PUBLIC_PS_WEB_DEMO_MODE=true`.

### 3.2 AI brief panel (REQ-WB-042)
- Side-by-side: raw buyer text (verbatim, escaped) and AI summary/category/confidence from triage, "advisory; AI does not decide refunds" banner always visible above the panel, not just on hover.
- Draft messages (if the `/draft` feature is built, cut-list item 5) are marked "draft, not sent" with no send button wired to anything real.
- Policy decision (from resolution, not triage) is rendered in a visually separate card with its own heading, so a merchant cannot mistake the AI output for the decision.

### 3.3 Policy view (REQ-WB-043)
- The 3 hardcoded rules (refund cap, category exclusions, velocity) rendered read-only with an ILLUSTRATIVE label on every numeric threshold (e.g. "~$50 cap - illustrative, not a real policy"), plus a per-case "which rules fired" breakdown sourced from `decision.reasons[]`.

### 3.4 Human-review queue (REQ-WB-044)
- AG Grid: case id, kind, reason codes, age, SLA state (`WITHIN`/`OVER`/`NO_TARGET` from `GET /review/queue`) - SLA target is explicitly labelled illustrative/demo when present.
- Detail pane (outside the grid, per R10 accessibility note) with Override action -> `POST /cases/{id}/merchant-action {"type":"OVERRIDE_OFFER"}`. UI states plainly: "This creates a new offer. The buyer must still approve it. No money moves yet."

### 3.5 Audit log (REQ-WB-045)
- AG Grid over `GET /audit/entries` (via BFF), columns: seq, type, actor_type/actor_id, ts, record_hash (truncated, full on row expand).
- "Verify chain" button calls `GET /audit/verify`; result banner (OK/FAILED) shown prominently, with head hash displayed and a copy-to-clipboard control, plus chain epoch (so judges understand a demo reset starts a new epoch, not that history was deleted).

### 3.6 REFUNDS_FROZEN switch (REQ-WB-046)
- Reads `GET /controls/refunds-frozen`; toggling requires a non-empty reason (matches `REASON_REQUIRED` 422) and a confirm step. Frozen state shown on merchant UI and, on the buyer side, as the neutral `queued_reason: REFUNDS_FROZEN` note "Refunds are paused for review" (never "frozen" or any alarming word to the buyer).

### 3.7 Demo reset (REQ-WB-047)
- Visible only in demo mode; requires typed confirmation (e.g. type "RESET"); calls the admin-token-protected reset endpoint; shows the new chain epoch after completion.

## 4. Guardrail demo scenes (mapped to test-strategy.md E-series and sprint-plan storyboard)
| Scene | What happens on screen | Proves |
|---|---|---|
| Over-cap block | Cart hard-blocked, no Confirm button, plain reason | AI/manual cart cannot exceed mandate cap |
| Hostile catalog text | Seeded item description with injection-style text; cart still only contains valid SKUs/qty, no hard block bypassed | Untrusted text cannot change money fields |
| LLM down / kill switch | `AI_PAUSED`/`NO_PROPOSAL` -> manual cart works unchanged | Fail-closed, no dead end |
| Injected carrier/report text | Report screen shows neutral "person is reviewing" status, no refund | Prompt injection cannot move money via triage |
| Revoke mid-flow | Revoke mandate -> next cart attempt hard-blocked immediately | Stop wins, no cache lag |
| REFUNDS_FROZEN | Approved offer stays `APPROVED`, buyer sees "paused for review", merchant sees frozen switch | Kill switch blocks execution, not approval |
| Audit verify | Verify-chain button returns OK after the full story, head hash shown | Tamper-evident log, not "tamper-proof" (never claimed) |

## 5. Copy rules
- Banned words/phrases (never render, source-lint AND runtime-crawl test, REQ-WB-004, matches auth-gateway sec 9 "must not say" list): "PayPal-backed", "PayPal-verified", "PayPal-protected", "legally binding", "non-repudiable", "compliant" (SOC2/PCI/etc.), "fraud-proof", "production-secure", "injection-proof", "real carrier data", "tamper-proof", "zero trust achieved", "flagged", "suspicious", "fraud", "abuse" (the last four specifically banned from any buyer-facing human-review copy, per 04 Test D).
- Required labels wherever such data appears: SIMULATED (carrier data, demo clock effects, force-status controls), CACHED (any cached/golden LLM response - must render the exact `badge` string from the API, not a shortened version), ILLUSTRATIVE (policy numbers, demo protection window, SLA targets, any other proposed-not-measured number).
- Persistent, non-dismissible SANDBOX banner on every page (REQ-WB-002): "Sandbox only. No real money. Seeded catalog. Simulated carrier."
- Footer disclosure on every page: "Not affiliated with or endorsed by PayPal."
- Server-owned text (receipt disclosures, offer "why", revoke message_code, review-queue brief, case reason text) is rendered verbatim from the API response, never paraphrased or strengthened by the client.
- All free text from any actor (buyer report, AI draft/summary, reviewer display name, carrier note) renders as plain text only.

## 6. Accessibility basics (REQ-WB-053)
- Full keyboard operability for every control, including AG Grid cells/rows (arrow-key nav, Enter to open detail pane which lives OUTSIDE the grid per R10) and the theme toggle.
- Visible focus indicators (not solely color), logical tab order matching visual order, `aria-live` region for async states (waking, confirming, submit results).
- Form labels explicit (`<label for>` or `aria-label`), error messages associated via `aria-describedby`.
- Color contrast meets WCAG 2.1 AA minimum in both light and dark themes (I target, no measured number invented).
- 200% browser zoom usable without horizontal scroll loss of function on buyer screens.
- `prefers-reduced-motion` respected: no animation on toggle/loading beyond a simple opacity/spinner fallback.
- Automated axe checks in Playwright on every key screen (0 serious/critical violations, REQ-WB-053 acceptance).

## 7. Responsive minimum (REQ-WB-054)
- Buyer flow: fully usable from 320px width (mandate sign, cart, checkout handoff, receipt, case screens) - single column, no horizontal scroll, tap targets >=44px (I heuristic).
- Merchant views: usable from tablet width (~768px) upward; AG Grid columns collapse/hide low-priority columns below that width or merchant screens show a "use a wider screen" notice rather than a broken grid - no claim of full merchant usability below tablet width.

## 8. Demo reset control
- See section 3.7 (buyer-visible effects) and merchant REQ-WB-047. UI-side: reset is a single button behind `NEXT_PUBLIC_PS_WEB_DEMO_MODE`, typed confirmation, disabled while the request is in flight, success toast states the new chain epoch number so judges resetting between each other's sessions understand prior data is not deleted, just epoch-separated (R11).

## 9. AG Grid usage (sponsor-prize candidate; R8/cut-list item 1)
- Used only for: merchant orders table (3.1), human-review queue (3.4), audit log (3.5). Community edition features only: client-side row model, sort, filter (text/set), column pinning, custom cell renderers (status/SIMULATED badges, hash truncation with copy), CSV export. No row grouping, no server-side row model, no Enterprise-gated feature - license risk R8 is closed by this constraint, confirmed again before S4-01 (sprint-tasks.md).
- Row detail (case detail, audit entry full payload) renders in a pane OUTSIDE the grid, never a grid master/detail Enterprise feature, both for license safety and for the a11y requirement in R10.
- README section "How we use AG Grid" documents exactly these three screens and the Community-only constraint, per S4-01 deliverable.

## 10. Tech choices
- Framework: Next.js (TypeScript) - ADR-002, REQ-WB-001. Package manager: pnpm (ADR-009 monorepo layout: `services/web`).
- UI/animation/visual stack (confirmed user decision 2026-10-10, not an ADR - see tech-stack.md sec 3.1): **Framer Motion + Next.js + shadcn/ui + WebGL + Aceternity UI**. shadcn/ui is the baseline component layer for every screen. Framer Motion and Aceternity UI/WebGL effects are used selectively, per the WHERE rule immediately below - this is binding, not a suggestion, because it is what keeps the honesty/trust copy rules (sec 5, sec 12 of prd.md) legible.
  - **WHERE used**: the opening hook/landing moment (`/`, persona picker) and transitions between major sections (e.g. route-level page transitions, section reveals on `/about`). These are non-money-path screens where visual impact helps the 3-minute judge demo land.
  - **WHERE NOT used** (plain shadcn/ui + light Framer Motion only - simple opacity/fade, no WebGL, no Aceternity): mandate signing form (sec 2.1), cart/checkout approval and the PayPal handoff explainer (sec 2.3-2.6), receipt (sec 2.8), refund offer/approve (sec 2.10), out-of-terms approval (sec 2.11), audit log/verify-chain (sec 3.5), human-review queue (sec 3.4 merchant view, sec 2.12 buyer-facing status). These are exactly the screens carrying money/trust information (amounts, mandate terms, SIMULATED/CACHED/ILLUSTRATIVE labels, banned-claims-governed copy, sec 5) that judges and research participants (04 Test A/B/D) must be able to read without animation competing for attention or risking a WebGL hydration/paint delay on a screen with a hard honesty-label acceptance criterion (prd.md REQ-WB-003/004).
  - Rationale cross-ref: tech-stack.md sec 3.2 "Frontend technical risk notes" (WebGL compatibility, bundle-size, SSR-hydration risk, Aceternity component weight) - this spec's WHERE rule is the mitigation tech-stack.md records.
- Rendering: no SSR of authenticated data (REQ-WB-010-safe non-goal in prd.md sec 4) - client-rendered app shell behind the session check; marketing/landing and `/about` can be static. WebGL/Aceternity components on the landing route are client-only (`ssr: false`/dynamic import), never part of the authenticated app shell.
- Styling: CSS variables/design tokens (light/dark/system theme, REQ-WB-007) with a small utility layer; shadcn/ui's Tailwind-based token conventions are the baseline (token system - colors, spacing, type scale - must exist before component work starts, ArchitectUX foundation-first principle).
- Data fetching: typed API client generated from `contracts/openapi/api-gateway.json` (REQ-WB-058); runtime response validation via zod with graceful unknown-field tolerance (`extra=forbid` on the server side does not mean the client should break on an added-but-ignored field in an additive-only contract change, ADR-008).
- No PayPal JS SDK, no card fields, no PayPal logos/trademarks anywhere (prd.md sec 4 non-goals) - approval is a plain redirect; the handoff explainer screen (sec 2.6) is one of the WHERE-NOT-used screens above, so it stays plain shadcn + light Framer Motion.
- AG Grid Community for the three screens in section 9.

## 11. State management
- Server is the sole source of truth for money, mandate, policy and case state; the client holds only: current session/CSRF token (in memory, never localStorage, REQ-WB-011), in-flight request/loading state, ephemeral form input, and cached read responses with short TTL for display (e.g. cart screen re-render) - never used to make authorization decisions.
- Prefer a thin server-state cache (e.g. a query-cache pattern) over a global client store; there is no client-owned business state to keep in Redux/Zustand-style stores because the client computes nothing authoritative.
- Idempotency-Key generated client-side per mutating action (UUID), persisted only for the lifetime of that in-flight action/retry, discarded after success (REQ-WB-051).

## 12. Error, loading, and cold-start states
- Global error boundary: any unhandled client exception shows a generic "Something went wrong" screen with a retry and a link to `/about`, never a stack trace.
- Loading: skeleton or spinner per screen, `aria-live="polite"` status text ("Loading your mandate...").
- Cold-start "waking up" UI (REQ-WB-050): triggered when a BFF call exceeds a short initial-timeout threshold (I heuristic, tuned in implementation, not invented here) with no response yet; shows "Waking up the demo server - this can take about a minute on a cold start (sandbox free-tier hosting)." with a progress indicator and automatic retry with backoff for idempotent calls only (reads and any call carrying an `Idempotency-Key`).
- Background warm-up ping fires on landing page load (hits `/healthz` style endpoint via BFF) so the wake often completes before the buyer reaches a mutating screen.
- After repeated failures (give-up threshold, tuned in implementation): "offline-video banner" - a static fallback explaining the hosted demo may be asleep, with a link/thumbnail to the recorded video, per REQ-WB-050.
- 401 anywhere -> "Your demo session ended" screen with one-click new-session button; safe in-progress form text (never money-sensitive fields) preserved via local component state only, not persisted to storage (REQ-WB-012).

## 13. Config / env names
All public values are prefixed `NEXT_PUBLIC_`; everything else lives only in Vercel's server-side env (never in the client bundle). Exact platform secret values are never in this repo (deployment.md sec 2 has the full table); names only, by convention `PS_WEB_*` for this service's own config and `NEXT_PUBLIC_PS_WEB_*` for client-exposed ones:
| Name | Client-exposed | Purpose |
|---|---|---|
| `NEXT_PUBLIC_PS_WEB_DEMO_MODE` | yes | Enables demo-only controls (reset, clock panel, scene shortcuts) |
| `NEXT_PUBLIC_PS_WEB_API_BASE` | yes | Same-origin `/api` rewrite target label (display/debug only, not a cross-origin call target) |
| `NEXT_PUBLIC_PS_WEB_PAYPAL_APPROVE_HOST_ALLOWLIST` | yes | Open-redirect guard host allowlist for `approve_url` (sec 2.6) |
| `PS_WEB_GATEWAY_INTERNAL_URL` | no | Server-side rewrite/proxy target for `/api/*` (Vercel rewrite to the Render gateway) |
| `PS_WEB_SENTRY_DSN` | no (if Sentry used) | Error tracking, optional |
No PayPal credentials, no HMAC/JWT keys, no DB URL ever appear here - `web` holds none of those (service-map.md sec 2 "web... Owns: nothing").

## 14. Open questions / conflicts (do not resolve here; logged for PM/architecture)
- Revoke semantics for already-captured orders: prd.md sec 8 says web assumes "protection for completed purchases stands"; auth-gateway sec 6 and sprint-plan sec 13 both flag this as still needing PM confirmation. This spec's copy (sections 2.2, 2.11) follows the P assumption and must be updated if PM decides otherwise.
- Exact BFF endpoint names/paths are not yet committed in service-map.md for several screens (reviewer queue exposure, approvals, controls/refunds-frozen) - resolution/checkout/mandate api.md files above the gateway are the cited source; api.md (this folder) lists the gap explicitly rather than inventing gateway paths.
- Monorepo note: this spec assumes `services/web` inside the single public monorepo (ADR-009), consistent with service-map.md and prd.md; no other file in this folder contradicts that, so nothing to flag beyond restating it.
- Merchant persona entry (one-click vs published demo password) - prd.md sec 8 leaves this open; both are compatible with this IA (landing persona picker just needs one more button/field either way).
- Reviewer role placement: built as a merchant-side screen/self-asserted name field per prd.md sec 8 decision, not a separate login - matches auth-gateway sec 1 reviewer actor definition (self-asserted name).
- Whether `shopping-agent /propose` ever returns a "golden/cached" mode in production vs only in dev fixtures is not settled; UI handles the `source:"cached"` case regardless (sec 2.3), so this is a backend decision, not a UI blocker.
- tech-stack.md did not exist at write time; if it is added later and conflicts with ADR-002/009 framework/hosting choices used in section 10, tech-stack.md wins and this file must be updated.
