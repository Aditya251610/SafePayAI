# web - Test Plan

Labels: V verified, VC vendor claim, I inference/unverified. Built on test-strategy.md (Master Test Strategy); test IDs below are `web`-specific and map to that doc's L5 e2e / L1 unit layers and the E/T/C series already defined there. All thresholds are our own heuristics (test-strategy.md sec 1 "honest reporting" principle) - no invented numbers beyond what test-strategy.md already states.

## 1. Component tests (L1-equivalent for web; Jest/Vitest + React Testing Library)
- Mandate preview/sign form: renders fields from `preview` response, nonce round-trip, amounts shown in major units with currency, integers never rendered raw (REQ-WB-021).
- Cart screen: renders `checks[]` for PASS/BLOCK/TIGHTEN; BLOCKED state never renders a Confirm control (not just disabled) - REQ-WB-025 component test.
- Receipt: snapshot test against the forbidden-claims list (test-strategy.md T25) - "PayPal-backed", "legally binding", etc. absent; `disclosures[]` rendered verbatim, not paraphrased.
- Offer card: Approve/Decline render with equal size/weight (visual-regression or DOM-attribute assertion, not just "both present").
- Human-review status: copy test against the banned-word list (spec.md sec 5: "flagged", "suspicious", "fraud", "abuse" absent) - ties to test-strategy.md 04 Test D.
- Theme toggle: light/dark/system persists across reload, no flash of unstyled content (REQ-WB-007).
- CACHED badge renderer: renders the exact `badge` string from the API response, never a shortened/invented version (shopping-agent api.md sec 4).
- AG Grid cell renderers (SIMULATED badge, hash truncation + copy): unit-tested renderer output independent of the grid itself.
- Injection rendering: buyer free text and AI draft text rendered as plain text; `dangerouslySetInnerHTML` banned via an ESLint rule with a test asserting the rule is active (REQ-WB-006).
- Idempotency-Key generation: unique per mutating action, discarded after success, resend-safe on retry (REQ-WB-051).
- Open-redirect guard: `approve_url` host validated against `NEXT_PUBLIC_PS_WEB_PAYPAL_APPROVE_HOST_ALLOWLIST` before navigation; mismatched host blocks navigation and logs (REQ-WB-027).

## 2. Contract/type tests
- Generated TypeScript types from `contracts/openapi/api-gateway.json` compile against every BFF call site (REQ-WB-058).
- zod runtime validators: known-good fixture from each upstream api.md (mandate, checkout, resolution, shopping-agent) parses successfully; an added-but-unknown field is tolerated (graceful unknown-field tolerance, additive-only contract assumption, ADR-008); a removed/renamed required field fails the test loudly (breaking-change guard).

## 3. E2E Playwright - demo path (2:45 target, aligned to sprint-plan.md storyboard and test-strategy.md L5 E1/E2)
Fixed test-id selectors, no sleeps (auto-wait), each test seeds its own mandate via API (test-strategy.md L5 rules), traces+video on failure.

| ID | Scene | Steps | Assertions |
|---|---|---|---|
| WEB-E01 | Buyer happy path | start session -> preview+sign mandate -> intent -> agent cart (cached or live) -> confirm -> PayPal approval (stubbed via double in CI; real click only in manual rehearsal, test-strategy.md L7) -> return -> receipt | Mandate signed; cart checks shown; receipt shows "Protected until day X (demo)" + sandbox banner; stopwatch assertion <= 2:45 end-to-end against the demo double (mirrors sprint-plan.md S3 rehearsal target <=2:50; CI run is a proxy, not the live-click timing) |
| WEB-E02 | Hero loop (merchant side) | merchant adds tracking -> advance demo clock -> LATE detected -> case appears in review-adjacent screens -> offer created inside terms -> buyer accepts -> refund completes | SIMULATED CARRIER banner visible throughout; offer card shows exact amount + "software rules decided this, AI did not"; audit verify returns OK after |
| WEB-E03 | Audit verify | open audit log grid -> click Verify chain | OK banner, head hash shown + copyable, chain epoch displayed |

## 4. E2E Playwright - failure / guardrail paths (maps to test-strategy.md E3-E12, C-series)
| ID | Scene | Maps to | Assertions |
|---|---|---|---|
| WEB-F01 | Over-cap cart blocked | test-strategy E5 | No Confirm button rendered; plain-language OVER_CAP reason shown |
| WEB-F02 | Revoked mandate blocks confirm | E6 | Cart attempt after revoke shows hard block immediately, no cache lag |
| WEB-F03 | LLM kill switch / AI_PAUSED | E7, C8-C10 | Manual cart fully usable; no dead end; no error chrome for a fail-closed 200 |
| WEB-F04 | Hostile catalog text (injection scene) | test-strategy E3 | Cart contains only valid SKU/qty; no hard block bypassed; no raw hostile text echoed as instructions |
| WEB-F05 | Injected report/carrier text | E4 | Human-review neutral status shown; no refund; no accusatory wording |
| WEB-F06 | Cold-start "waking up" | deployment-zero-cost risk; REQ-WB-050 | Waking UI shown instead of blank page/raw error; retry succeeds once warm; offline-video fallback banner after give-up threshold |
| WEB-F07 | Offer outside terms -> approval link | E8 | Link preview shows exact terms; replay rejected (409); reused/expired link shows neutral copy |
| WEB-F08 | REFUNDS_FROZEN | E9 | Accepted offer execution shows `QUEUED_FROZEN`; buyer sees "refunds are paused for review", never "frozen" |
| WEB-F09 | Buyer B cannot open buyer A's order/case/approval | E10, T10 IDOR | 404-style generic message, no existence oracle leak |
| WEB-F10 | PayPal 5xx on create order | E11, C1 | Friendly retry copy; no duplicate order created (idempotency key) |
| WEB-F11 | Session expiry mid-flow | E12, REQ-WB-012 | "Your demo session ended" screen; one-click new session; no leaked in-progress money-sensitive data |
| WEB-F12 | Return with bad/missing state, cancel, sign-in-required | REQ-WB-028 | Every documented return code (spec.md sec 2.7) maps to its own specific, non-alarming copy - never a generic "payment failed" when the true state is unknown |
| WEB-F13 | Free-text injection corpus on report screen | T7 injection corpus (stub in CI) | No URL/amount echoed in any derived UI text; long input handled; HTML-looking input rendered as text, not executed |

## 5. Visual checks of honesty labels (crawl test, maps to REQ-WB-003/004)
- Screenshot-diff or DOM-text-crawl across every screen in spec.md sec 2/3 asserting presence of required labels (SIMULATED, CACHED, ILLUSTRATIVE) wherever the corresponding data type appears, and absence of every banned phrase (spec.md sec 5 list = auth-gateway.md sec 9 "must not say" list).
- Persistent SANDBOX banner present and non-dismissible on every route (REQ-WB-002) - test asserts it survives a simulated dismiss-attempt (no close button exists).
- Footer "Not affiliated with or endorsed by PayPal." present on every route.
- This crawl runs both against rendered DOM text (post-hydration) and against source copy (lint rule) - two independent passes, matching REQ-WB-004's "CI lint on source copy + runtime crawl of rendered text."

## 6. Accessibility checks (axe + manual, maps to REQ-WB-053)
- Automated axe-core scan in Playwright on every key screen listed in spec.md sec 1 IA: 0 serious/critical violations required to pass CI.
- Keyboard-only run-through of: mandate sign, cart (including BLOCKED state), offer accept/decline, AG Grid rows (orders, review queue, audit log) with Enter opening the detail pane outside the grid (R10).
- Focus-visible check on every interactive control, including the theme toggle and grid cells.
- 200% zoom check on buyer screens (no horizontal scroll loss of function, REQ-WB-054).
- `prefers-reduced-motion` respected check (no animation beyond opacity/spinner fallback).
- Color contrast check (axe) in both light and dark theme for every key screen.

## 7. Responsive / visual suite
- 320px viewport run of the full buyer path (WEB-E01 at mobile width) - no horizontal scroll, tap targets usable.
- Tablet-width (~768px) run of merchant screens; below that width either columns collapse gracefully or a "use a wider screen" notice appears - asserted explicitly, not just "doesn't crash" (REQ-WB-054).

## 8. CI structure (side by side with backend workflows)
- Path-filtered GitHub Actions workflow triggered on `services/web/**` changes only (matches sprint-plan.md "GitHub Actions per-service: path-filtered workflows").
- Stages: lint (ESLint incl. the `dangerouslySetInnerHTML` ban rule and the banned-word source lint) -> typecheck -> unit/component (Jest/Vitest) -> contract/type check against committed OpenAPI -> build (and a build-output check that MSW/mock code is absent from the production bundle, per deployment.md sec 7 open item) -> Playwright e2e against the Profile A compose stack (test-strategy.md L4/L5 environment) -> axe a11y suite.
- Required-green gate before merge, mirroring test-strategy.md sec 8's per-sprint gating table; `web`'s own required set for each sprint:
  - S1 (test-strategy.md S1 row + sprint-tasks.md S1-10): lint/types/build; component tests for mandate sign + manual cart + over-cap block; Playwright happy-path-so-far + a11y on those screens.
  - S2 (S2-08): + WEB-E01 cut-line path, WEB-F02 revoke, WEB-F06 waking-up, receipt forbidden-claims snapshot.
  - S3 (S3-09): + WEB-E02 hero loop, WEB-F04/F05 injection scenes, WEB-F07/F08 approval link and freeze, full honesty-label crawl.
  - S4 (S4-01): + AG Grid Playwright checks (sort/filter/export/keyboard nav), full WEB-F01-F13 set, full axe suite across all screens, responsive suite.
- Flake policy: inherits test-strategy.md sec 9 (max 1 retry in e2e only, never in unit/contract; quarantine within 24 h, max 5 quarantined, fix-or-delete within 5 days; honesty-label and IDOR-style tests on `web` are not money-path invariant tests per se but any Sev1 (false claim on screen) cannot be quarantined, per test-strategy.md sec 14).

## 9. Definition of done (per feature, matches sprint-plan.md standing rule)
A `web` feature task is done only when ALL of:
1. Component/unit test exists and is green in CI.
2. If the feature touches a demo-path or guardrail scene, its Playwright twin (section 3 or 4) exists and is green.
3. If the feature renders server-supplied data that could carry a claim, the honesty-label/banned-word crawl (section 5) covers that screen.
4. If the feature is interactive, it passes the axe check and a keyboard-only pass (section 6).
5. Deployed to the hosted Vercel environment (preview or production per deployment.md sec 2) and smoke-checked (screen renders, no console errors, no leaked secrets in the client bundle).
6. No new banned phrase introduced (lint + crawl both green).

## 10. Open items
- Exact cold-start initial-timeout/give-up thresholds for WEB-F06 are implementation-tuned (spec.md sec 12 / deployment.md sec 5); the test asserts behavior (waking UI appears, then fallback banner), not a specific millisecond value.
- Live-click PayPal approval (real sandbox UI) is never part of default `web` CI per test-strategy.md L7 scoping; WEB-E01's PayPal step is the adapter-double stub in CI and a manual rehearsal item in the weekly demo checkpoints (sprint-plan.md sec 10) - this test-plan does not claim CI covers the real click.
- Tracking service's api.md was not reviewed for this doc (per the task's scope); merchant tracking-form component/e2e tests reference the P-flagged BFF routes in api.md sec 7 and must be revisited once `services/tracking/api.md` exists.
