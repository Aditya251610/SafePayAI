# PRD: SafePayAI Platform (working name)
**Status**: Draft v0.1  **Author**: Alex (PM)  **Last updated**: 2026-10-10
**Labels**: V verified, VC vendor/secondary claim, I inference/assumption, H our own heuristic. No invented numbers; "unknown" means unknown.
**Inputs**: 00-context-brief, 01-market-study, 02-product-market-fit, 03-hackathon-win-probability, 04-user-research-and-validation-plan, 05-submission-and-launch-plan, architecture/service-map.

---

## 1. Vision and pitch
- **One-liner**: Buyer-signed purchase protection. A Mandate fixes what an agent may buy and what is refunded if it does not arrive; a bounded agent only proposes carts inside it; a deterministic loop detects late/lost orders and refunds under pre-authorized terms.
- **Vision (I)**: agent-era purchases come with a remedy agreed BEFORE the purchase, executed without a claim form, with AI helping but never deciding money.
- **Positioning**: protection is the hero; the agent is a bounded, secondary step (~25% of demo runtime). We do not replace PayPal Buyer Protection and do not claim to.
- **Goal now**: win/place in the PayPal AI hackathon (target submit 2026-11-10; deadline 11-12, time/timezone unconfirmed, trust the Devpost timer).

## 2. Problem statement
- **Who**: online buyers (human or agent-assisted) and small merchants paid via PayPal.
- **Pain (buyer)**: item-not-received claims are manual, ~14 days average (VC/I); app tracking is separate from the web-only Resolution Center (V); no proactive late alert or auto-refund found (I, absence of evidence).
- **Pain (merchant)**: dispute fee $15, chargeback fee $20, Mastercard average chargeback cost $128 (V); ~90% see refund/policy abuse as significant, 65% review manually (VC).
- **Pain (agent trust)**: 19% trust AI for everyday purchases, 60% would quit after one mistake, 53-71% want approval (all VC). ChatGPT Instant Checkout was scaled back Mar 2026 (V).
- **Gap (I)**: mandate protocols stop at "authorized to pay"; post-purchase tools are merchant-side or card-dispute-side; no researched player combines buyer-signed refund terms with automatic delivery-failure detection.
- **Cost of not solving**: unknown in dollars (delivery-failure share of PayPal's ~$1.3B FY2025 transaction losses is unknown, V). We make no economic claim.
- **Honest caveat**: this is a demonstration, not validated demand. Zero real users exist.

## 3. Personas (hypotheses, see doc 04)
| ID | Persona | Goal | Key need from product |
|---|---|---|---|
| P1 | Cautious online buyer | Do not chase a refund if the order is late | Readable Mandate; explicit approval; receipt stating what is protected until when (demo window) |
| P2 | Policy-bound small merchant | Refunds only inside rules I set; humans handle odd cases | Predictable policy; clear reason when a case goes to a human |
| P3 | Delegation-wary power buyer | Hard limits, revoke any time, proof AI cannot move money | Cap/allowlist/revoke; audit verify; fresh approval outside terms |
| P4 | Hackathon judge / PayPal developer advocate or PM | Understand in under 5 minutes; check honesty and PayPal depth | Video, README, hosted demo, judge guide, no overclaims |
| P5 | Reviewer (merchant-side human) | Decide HUMAN_REVIEW cases fast | Queue, read-only AI brief, reasons |

## 4. User stories
**Buyer**
- B1: As a buyer, I sign a Mandate (allowlist, max total, intent, expiry, protection terms) so the agent cannot exceed what I agreed.
- B2: As a buyer, I type an intent and see a proposed cart with plain-language check results so I know why it was allowed or blocked.
- B3: As a buyer, I approve the payment myself in the PayPal sandbox so nothing is charged without my click.
- B4: As a buyer, my receipt says what is protected and until when (labelled demo window) so I do not over-assume.
- B5: As a buyer, if the order is late/lost I get a refund offer inside the terms I signed, with no claim form.
- B6: As a buyer, I can report a problem in free text and get a neutral, clear next step.
- B7: As a buyer, anything outside my signed terms needs my fresh single-use approval.
- B8: As a buyer, I can revoke the Mandate and see the effect (see decision D1).

**Merchant**
- M1: As a merchant, I add tracking to an order so the protection loop can monitor it.
- M2: As a merchant, my refund policy (cap, category exclusions, velocity) is applied deterministically so liability is bounded.
- M3: As a merchant, I see why a case was refunded, offered, or sent to a human.
- M4: As a merchant, an override creates a NEW offer the buyer must approve, never a direct refund.

**Reviewer / judge**
- R1: As a reviewer, I see a queue of HUMAN_REVIEW cases with a read-only AI brief and the deterministic check results.
- R2: As a judge, I run the full flow on the hosted demo in under 5 minutes, including a pre-seeded late order.
- R3: As a judge, I verify the audit chain and see what is simulated vs real.

## 5. Product principles
1. AI never decides money or sets amounts; deterministic server-enforced policy executes.
2. Fail closed: error, timeout, low confidence, schema failure -> HUMAN_REVIEW or hard block.
3. The server derives merchant, amount, currency, capture_id. Client and model values are ignored.
4. Untrusted text (buyer free text, catalog text, carrier notes) is data, never instructions.
5. Only paypal-adapter holds PayPal credentials; LLM services have no money path.
6. Honesty on screen: SANDBOX, SIMULATED CARRIER, SEEDED CATALOG, demo window labels always visible.
7. Reasons for every decision, in plain words.
8. Unknown refund outcome is reconciled by lookup, never blind retry.
9. Scope is cut to the demo path; anything untested in PayPal sandbox is not on it.

## 6. End-to-end journeys

### 6.1 Demo path (target 2:45; ties to storyboard in doc 05)
| Time | Step | Services | Visible proof |
|---|---|---|---|
| 0:00-0:15 | Hook: problem statement, SIMULATED CARRIER label | web | Label on screen |
| 0:15-0:40 | Buyer signs Mandate | web, api-gateway, mandate, audit | Plain summary; revoke visible; mandate hash in details |
| 0:40-1:05 | Intent -> agent cart -> a hard block (over cap) shown | shopping-agent, catalog, checkout, mandate | Check results with reasons; advisory AI note labelled |
| 1:05-1:30 | Real sandbox approve click, capture, receipt | checkout, paypal-adapter | Receipt with reasons and "Protected until day X (demo)" |
| 1:30-1:55 | Merchant adds tracking; demo clock advanced; LATE detected | tracking, paypal-adapter | Case enters PROBLEM_DETECTED |
| 1:55-2:25 | Triage (enum+confidence), policy, 9 checks, refund, sandbox shows refund | resolution, triage-ai, paypal-adapter | PayPal refund id; offer inside terms |
| 2:25-2:45 | Audit verify; failure case -> HUMAN_REVIEW | audit, resolution | Chain verified; neutral escalation message |
| 2:45-2:55 | Title card: URL, repo, "sandbox only" | web | - |
- Video shows 5 key states, not all 12 (H, scope discipline).

### 6.2 Failure and guardrail paths
| # | Trigger | Expected behavior | Service |
|---|---|---|---|
| F1 | Cart over cap / merchant not allowlisted / unknown SKU / qty cap / currency mismatch / agent price != DB / mandate revoked or expired | Hard block with reason; advisory AI cannot override | mandate, checkout |
| F2 | LLM invalid output or timeout (cart) | Degrade to manual cart / NEEDS_BUYER_CONFIRMATION | shopping-agent |
| F3 | Buyer abandons or declines PayPal approval | Order not captured; no protection starts | checkout |
| F4 | Capture fails | order.capture_failed; no protected case created | checkout |
| F5 | Triage low confidence / schema failure / error | OTHER -> HUMAN_REVIEW | triage-ai, resolution |
| F6 | Claim outside signed terms or over merchant cap | No auto-refund; fresh buyer approval link (single-use, proposal_hash bound) or human review | resolution |
| F7 | Buyer velocity > 2 refunds/30 days (illustrative) | HUMAN_REVIEW, neutral wording | resolution |
| F8 | Refund call returns 409 / unknown | Treated as in-progress; reconcile by GET refund; no blind retry | paypal-adapter, resolution |
| F9 | Refund 422 over-refund or DUPLICATE_INVOICE_ID | Refund fails safely; case to review; no second attempt without new decision | paypal-adapter, resolution |
| F10 | Mandate revoked mid-flight | Un-captured carts blocked; effect on earned protection per decision D1 | mandate, checkout, resolution |
| F11 | Prompt injection in free text or catalog text | AI output only fills enum/draft; regex gate on drafts; amounts never from AI | triage-ai, resolution |
| F12 | Audit service down | Events queue in producer outboxes; refund start requires local outbox write | audit, resolution |
| F13 | PayPal token 401 | Refresh and retry once (token behavior V) | paypal-adapter |
| F14 | Hosted service cold start | "Warming up" state; pre-seeded late order available | api-gateway, web |

## 7. Feature list
Priority: P0 = required for demo/submission; P1 = strengthens score if time; P2 = stretch/post-hackathon.

| ID | Feature | Pri | Service(s) |
|---|---|---|---|
| FT-01 | Auth, sessions, internal tokens, routing, rate limit, BFF | P0 | api-gateway |
| FT-02 | Mandate create/sign (HMAC demo-grade), view, revoke, expire | P0 | mandate |
| FT-03 | Deterministic mandate evaluate (hard blocks) | P0 | mandate |
| FT-04 | Seeded catalog (~12 items, 3 virtual merchants), authoritative pricing | P0 | catalog |
| FT-05 | Agent cart proposal (structured, schema-validated) | P0 | shopping-agent |
| FT-06 | Advisory intent-fit (can only tighten) | P1 | shopping-agent |
| FT-07 | Cart check orchestration, order create, PayPal approval handoff, capture, receipt | P0 | checkout, paypal-adapter |
| FT-08 | PayPal REST wrapper with idempotency ledger | P0 | paypal-adapter |
| FT-09 | Own MCP server over verified REST (create_order, get_order, capture_order, add_tracking, refund_capture, get_refund) with per-tool caller allowlist | P0 (core to Agentic Commerce prize fit) | paypal-adapter |
| FT-10 | Merchant add-tracking + PayPal "tracking added" signal | P0 | tracking, paypal-adapter |
| FT-11 | Simulated carrier, demo clock, force late/lost, detector | P0 | tracking |
| FT-12 | Buyer problem report (untrusted free text) | P1 | resolution, web |
| FT-13 | AI triage (enum + confidence), fail closed | P0 | triage-ai, resolution |
| FT-14 | AI message drafts (regex gate: no URLs/amounts) | P1 | triage-ai |
| FT-15 | Reviewer brief (read-only) | P1 | triage-ai, resolution |
| FT-16 | Deterministic merchant policy (3 illustrative rules) | P0 | resolution |
| FT-17 | Case state machine (12 states) | P0 | resolution |
| FT-18 | Offer, accept, single-use approval link bound by proposal_hash | P0 | resolution |
| FT-19 | 9 ordered pre-refund checks + refund saga + reconcile | P0 | resolution, paypal-adapter |
| FT-20 | Merchant override as NEW buyer-approved offer | P1 | resolution |
| FT-21 | Human-review queue (AG Grid if sponsor prize chosen) | P1 | resolution, web |
| FT-22 | In-app notifications | P1 | resolution, web |
| FT-23 | Hash-chained audit log + verify endpoint | P0 | audit |
| FT-24 | Audit view with chain-status column | P1 | audit, web |
| FT-25 | Buyer UI (mandate, intent, cart, receipt, report, approve) | P0 | web |
| FT-26 | Merchant UI (tracking, queue, brief, override) | P0 queue/tracking, P1 override | web |
| FT-27 | Demo control panel, reset endpoint, seeded late order | P0 | web, tracking, api-gateway |
| FT-28 | Judge guide, README honesty section, labels on screen | P0 | web (repo docs) |
| FT-29 | Webhooks as hints, Disputes API, PENDING-refund handling | P2 (untested, not on demo path) | paypal-adapter, resolution |
| FT-30 | Buyer-held-key signing, real carrier feeds, email | P2 (out of scope now) | mandate, tracking |

## 8. Requirements
Format: REQ-PL-NNN; each has acceptance criteria (AC). Thresholds are H unless stated.

**Mandate and cart**
- REQ-PL-001 Mandate content. Mandate holds merchant allowlist, max total (integer minor units, incl. fees), intent text, expiry, protection terms, policy_version pin, nonce, hash, server HMAC. AC: all fields persisted immutably; amounts shown to users in major units with currency; internal integers never exposed in UI.
- REQ-PL-002 Plain-language signing. AC: summary precedes hash/HMAC details; cap, allowlist, expiry, intent, protection terms visible in one list; revoke path visible after signing; no text claims "legally binding", "PayPal-backed", "non-repudiable"; sandbox/demo label present.
- REQ-PL-003 Deterministic hard blocks. Evaluate blocks on: revoked/expired, merchant not allowlisted, total over cap, unknown SKU, quantity cap, currency mismatch, agent-stated price != DB. AC: one automated test per block reason; each returns a human-readable reason; no AI input can flip a block to allow.
- REQ-PL-004 Server-derived facts. AC: merchant, amount, currency, capture_id come from server data; a request carrying client values for these is ignored and a test proves it.
- REQ-PL-005 Server re-pricing. AC: cart totals computed from catalog; mismatch with agent-stated price blocks.
- REQ-PL-006 Agent proposal. Agent returns catalog item IDs + quantities only. AC: schema validation; invalid -> manual cart path; measured validity on a 20-prompt test is reported with the real number (target >=95%, not yet measured, I).
- REQ-PL-007 Advisory intent-fit. AC: runs only after hard checks pass; output in {PASS, NEEDS_BUYER_CONFIRMATION, REJECT_WITH_REASON}; labelled "advisory"; can only tighten; failure -> NEEDS_BUYER_CONFIRMATION.

**Payment**
- REQ-PL-008 Order creation. AC: PayPal order created with persisted PayPal-Request-Id; custom_id = mandate id, invoice_id set; replay returns same order (V).
- REQ-PL-009 Buyer approval and capture. AC: buyer approves on PayPal sandbox page; capture only after approval; capture result stored with capture_id; receipt generated.
- REQ-PL-010 Receipt. AC: shows items, total, mandate reference, reasons, "Protected until day X" labelled demo window not PayPal's, "refund is merchant-funded via PayPal refund", SIMULATED CARRIER label, next steps.
- REQ-PL-011 Credential boundary. AC: PayPal client id/secret exist only in paypal-adapter env; repo scan (gitleaks) clean; no LLM service has any PayPal credential or route to money endpoints.
- REQ-PL-012 Adapter idempotency. AC: adapter rejects calls without caller-supplied request_id; every outbound call recorded in ledger; 409 treated as in-progress/UNKNOWN; 401 triggers one token refresh.
- REQ-PL-013 MCP server. AC: tools listed in FT-09 exposed at /mcp; per-tool caller allowlist (checkout: orders/capture/track; resolution: refund/get; LLM services: none); `docs/mcp.md` with tool list and copy-paste config.

**Detection and triage**
- REQ-PL-014 Tracking signal. AC: merchant tracking entry calls PayPal add-tracking (201 V) as a "tracking added" signal only; late/lost status lives in our DB and is labelled SIMULATED CARRIER everywhere shown.
- REQ-PL-015 Demo clock and detector. AC: clock advance and force late/lost endpoints work; detector run is idempotent; a seeded late order is available so refund is visible within ~30 s (H).
- REQ-PL-016 Buyer report. AC: free text treated as untrusted; stored; passed to triage-ai as data only.
- REQ-PL-017 Triage. AC: output enum {LATE, LOST, DAMAGED, WRONG_ITEM, NOT_AS_DESCRIBED, OTHER} + confidence; any error, timeout, schema failure, or low confidence -> OTHER/HUMAN_REVIEW; triage output never contains or sets an amount.
- REQ-PL-018 Drafts. AC: regex gate rejects drafts containing URLs or amounts; rejected draft falls back to a static template.
- REQ-PL-019 Reviewer brief. AC: read-only; shown with deterministic check results; labelled AI-generated.

**Resolution and refund**
- REQ-PL-020 Merchant policy. Three hardcoded illustrative rules: refund cap (~$50), category exclusions, buyer velocity > 2 refunds/30 days -> human. AC: each rule has a test and a visible reason; values labelled illustrative, not tuned.
- REQ-PL-021 Terms check. AC: refund offered automatically only if inside the Mandate's pre-authorized terms AND merchant policy; otherwise fresh buyer approval or human review.
- REQ-PL-022 Approval link. AC: single-use, expiring, bound by proposal_hash; states exactly what it approves; reuse or altered proposal rejected.
- REQ-PL-023 Pre-refund checks. AC: 9 ordered checks (defined in resolution spec) run before any refund call; any failure stops the refund and records which check failed.
- REQ-PL-024 Refund execution. AC: refund_attempt with request_id persisted BEFORE the PayPal call; amount comes from policy + mandate terms + capture, never AI; success stores PayPal refund id; over-refund and duplicate-invoice errors handled (V cases).
- REQ-PL-025 Reconciliation. AC: unknown/409 outcome resolved via GET refund; reconcile endpoint is idempotent; never blind retry.
- REQ-PL-026 Merchant override. AC: override creates a NEW offer that needs buyer approval; no direct refund path from merchant action.
- REQ-PL-027 State machine. AC: only the 12 defined states and defined transitions; every transition recorded; UI shows plain-language state labels.
- REQ-PL-028 Escalation wording. AC: neutral text; none of the avoided words ("flagged", "suspicious", "fraud", "abuse", "violation"); states next step and that a person decides; no velocity reasoning exposed to buyer.
- REQ-PL-029 Revoke semantics. AC: per decision D1 once confirmed; until then default is the safest reading in D1.

**Audit and honesty**
- REQ-PL-030 Audit chain. AC: mandate, cart, order, refund (and AI proposal) events appended with prev_hash; DB role INSERT/SELECT only; triggers block UPDATE/DELETE; verify endpoint returns pass/fail and first broken seq; described as tamper-evident, not tamper-proof.
- REQ-PL-031 Audit idempotency and backlog. AC: append idempotent on event_id; producers' outbox retries when audit is down.
- REQ-PL-032 Honest labels. AC: SANDBOX, SIMULATED CARRIER, SEEDED CATALOG, demo window visible on relevant screens; claims checklist (section 10) passes with zero violations.
- REQ-PL-033 Demo reset. AC: token-protected reset returns the seeded state; starts a new audit epoch, documented.
- REQ-PL-034 Accessibility. AC: keyboard operable, visible focus, screen-reader labels, sufficient contrast, readable at 200% zoom on buyer approval, mandate, receipt screens.
- REQ-PL-035 Gateway. AC: all web traffic via api-gateway; internal tokens short-lived with audience per service; rate limits; no business logic in gateway.
- REQ-PL-036 Judge access. AC: hosted demo needs no signup wall; "Start here" with numbered steps; throwaway US sandbox buyer credentials in testing instructions (never real, never API keys); fallback banner pointing to video.
- REQ-PL-037 Abuse limits. AC: per-IP rate limit; hard LLM spend cap; idempotent actions so repeated judge clicks cannot double-refund.
- REQ-PL-038 No untested PayPal features. AC: no use of Fastlane, Vault v3, Agent Ready, Store Sync, WebMCP, production Payouts; webhooks and Disputes API not on demo path.

## 9. Non-goals
- Real money, real carriers, real merchants, real PayPal protection window.
- Generic autonomous shopping agent; price tracking; spend dashboards; chat invoicing; x402.
- Legal, regulatory, or compliance claims; buyer-held-key signatures (post-hackathon).
- Per-merchant accountability (single shared sandbox merchant login).
- Email notifications (in-app only).
- Merchant onboarding, multi-PSP, fraud modelling beyond 3 illustrative policies.
- Disputes API, webhooks, refund PENDING handling (untested; P2).
- Conversion lift or dispute-reduction claims.

## 10. Success metrics

### 10.1 Demo reliability (H targets)
| Metric | Target | Source |
|---|---|---|
| Consecutive full demo runs without manual fix | 10 (doc 03 indicator) | Test log |
| Hosted demo loads warm | <5 s (doc 05) | Smoke test |
| Seeded late order to visible refund | ~30 s (doc 05) | Manual timing |
| Scripted smoke test (mandate -> cart -> order create) | Runs every 6 h until 12-21, no unexplained failures | Cron |
| Cart validity on 20 prompts | >=95% target; report actual | Test |
| Video | <3:00; 3 outsiders state product in one sentence | Cold-view test |

### 10.2 Honest-claims checklist (all must be true at submit)
- [ ] No "PayPal-backed/verified/protected", "legally binding", "non-repudiable", "compliant", "fraud-proof", "production-secure", "injection-proof".
- [ ] No conversion-lift, loss-reduction, or dispute-reduction claim.
- [ ] Carrier labelled SIMULATED everywhere; catalog labelled SEEDED; sandbox labelled.
- [ ] "Protected until day X" labelled as demo window.
- [ ] Refund described as merchant-funded via PayPal refund.
- [ ] Vendor figures labelled as vendor claims; no prize total or active-account figure cited.
- [ ] README limitations section lists what was and was not tested.
- [ ] AI-coding-agent use disclosed.
- [ ] No PayPal logos/trademarks or music in video; "not affiliated with or endorsed by PayPal" in README.
- [ ] No secrets in repo; sandbox buyer credentials are throwaway.

### 10.3 Our own heuristics (from doc 04; H, tiny n, directional only)
- Mandate screen: >=80% correct on cap + allowlist + revoke; 0 participants think agent can exceed cap.
- Receipt: >=75% correct on window + "not PayPal's real window" + who pays; fail if >=3 of 8 think it is PayPal-backed.
- Comfort: median >=4 approval-gated, >=3 auto-refund inside terms.
- Escalation: 0 read as accusation; >=80% state next step.
- Merchant policy: >=3 of 4 case outcomes predicted correctly.
- Sessions: 8-10 buyer/merchant sessions target; reported as "N informal sessions", never as market validation.

### 10.4 Illustrative PayPal-owned metrics (NOT measured; no baseline or lift claimed)
| Metric | Why PayPal cares | Prototype can show |
|---|---|---|
| Time from problem signal to buyer resolution | Today ~14 days for INR claims (VC/I) | Minutes in demo only; production value unknown |
| Disputes per order | $15 dispute, $20 chargeback (V) | Nothing; needs pilot |
| Branded-checkout trust/conversion | Filing priority (V) | Nothing; not claimed |
| Transaction losses | ~$1.3B FY2025 (V) | Must not increase; abuse rate unknown |

## 11. Dependencies and assumptions
**Dependencies**
- PayPal sandbox: OAuth, Orders v2, capture, tracking, Payments v2 refund, GET refund (all V from spike).
- US personal sandbox buyer (India buyer cannot pay USD, V).
- LLM provider with schema outputs and a hard spend cap.
- Free-tier hosting and Postgres; Render free sleep/DB expiry facts (V per doc 05) conflict with N always-on services and the 12-21 winners date.
- Devpost official rules (not yet fetched).
- AG Grid Community if sponsor prize is chosen.

**Assumptions (I)**
- A1: Judges accept a simulated carrier if clearly labelled.
- A2: Return URL into our own server works (untested).
- A3: Sandbox refunds return COMPLETED (PENDING untested).
- A4: One real approval click in sandbox is acceptable in the demo.
- A5: Free-tier cold starts can be managed by pinging or fewer deployed units.
- A6: Review/test/video time (~33 days) is the real constraint, not build volume.

## 12. Open product decisions — RESOLVED 2026-10-10 (user confirmed, all 10)
| # | Decision | Options | PM recommendation (confidence) | **DECIDED** |
|---|---|---|---|---|
| D1 | What does "revoke" do to protection already earned on captured orders? | (a) Revoke stops only future carts; earned protection on captured orders stays; (b) revoke also cancels protection on open orders; (c) buyer chooses at revoke time | (a) with a clear on-screen statement. Reason: the merchant was paid under those terms; (b) makes the refund promise unreliable. ~70% | **(a)** Revoke = future spend only; protection already earned stands. |
| D2 | Is the buyer notified of auto-refunds, and before or after? | (a) After, in-app, with reasons; (b) offer first, buyer clicks accept; (c) silent | (a) for inside-terms refunds (matches pre-authorization), (b) for anything outside terms. ~65% | **(a)** In-app, after the refund, with reasons shown. |
| D3 | Merchant pre-authorization wording: who agrees to the terms and how is it shown? | (a) Merchant policy is a standing, displayed setting and the Mandate terms cannot exceed it; (b) per-order merchant acceptance; (c) implicit | (a). Must NOT imply merchant legally agreed (single shared login, no per-merchant accountability). Draft: "This shop's demo policy allows automatic refunds up to the cap shown. Sandbox illustration only." ~60% | **(a)** Standing displayed policy; explicitly not legal-agreement wording. |
| D4 | Sponsor prize choice | AG Grid (recommended in doc 05), Render, none | AG Grid; one sponsor prize only. ~65% | **AG Grid** is the primary build target (audit log + review queue). Render is also genuinely used as host (no extra work, no claim conflict). Channel3 skipped — would require abandoning the seeded-catalog architecture decision. Only one sponsor prize can be *awarded* per Devpost rules even if multiple tools are used. |
| D5 | Hosting shape: how many deployed units given free-hours and cold starts | 11 slugs deployed separately vs fewer processes (modular monolith for the demo, same service boundaries in code) | Needs architecture owner + user call; PM leans to fewer deployed units if free-tier hours cannot support 11 always-on (I) | **Fewer processes** (Profile B: edge/core/ai/paypal + web) per architecture/overview.md — already the documented default; not reopened. |
| D6 | Judge credentials: publish throwaway sandbox buyer login in Devpost | Yes (rotate after judging) / no (judges self-create) | Yes, throwaway only. ~70% | **Yes** — pre-seeded throwaway demo login published with the submission. |
| D7 | Protection window length for the demo and what "late" means | Unknown; must be a visible constant in policy config | User to pick the demo values; labelled illustrative | **5 days** past promised delivery triggers automatic late detection (illustrative/demo constant). |
| D8 | Shopping-agent runtime share if video runs long | Cut agent to 20-30 s vs keep ~25% | Cut first (doc 03) | **~30%** (~50s of 2:45). The agent segment flows directly into the real PayPal order/approve/capture, so it demonstrates agentic AI and PayPal-centrality in the same beat. |
| D9 | Product name | Keep "SafePayAI" vs rename after trademark/name-clash check | Check before Devpost page (I) | **"SafePayAI"** — final name, applied across all docs 2026-10-10. No trademark/name-clash check done yet; do before the Devpost page goes live (I, unverified). |
| D10 | What the buyer sees when merchant cap is hit but Mandate allows more | Fresh approval link vs human review first | Human review first, then offer if reviewer agrees. ~55% | **Human review first** — the stricter of the two caps always wins. |

Related naming decisions confirmed the same day: refund tool is named `refund_capture` (not `create_refund`); env var prefix convention is `PS_<SLUG>_*` (not `MW_<SLUG>_*`); license is MIT; Postgres driver is asyncpg; money-gating uses a single signed `authorization_ticket`; LLM call logs live in one shared `llm` schema. The SafePayAI and `refund_capture` renames have been mechanically applied across every file in this PRD tree. The `PS_` env-var prefix pass is now complete across all 11 `services/<slug>/` docs (spec.md/api.md/deployment.md and the rest), with three documented exceptions kept as-is rather than renamed: `PAYPAL_CLIENT_ID`/`PAYPAL_CLIENT_SECRET` (paypal-adapter, the exact names already used in the working, tested sandbox spike and real `.env`); `MANDATE_HMAC_KEY`/`MANDATE_HMAC_KEY_PREVIOUS` (mandate, because other services' CI env-manifest tests already forbid the bare name — see mandate/spec.md C5); and `INTERNAL_TICK_SECRET` (a deliberately unprefixed shared cron-trigger name consumed by mandate, checkout, and tracking). Shared/cross-service vars otherwise carry the prefix of the service that mints them (e.g. `PS_CHECKOUT_TICKET_HMAC_KEY`/`PS_RESOLUTION_TICKET_HMAC_KEY`, consumed by paypal-adapter but named after the minter).

## 13. Release criteria for submission (2026-11-10)
**Must (all)**
- [ ] All P0 features done; REQ-PL-001 to 038 P0-relevant ACs pass.
- [ ] Full demo path passes 10 consecutive runs on the HOSTED demo; seeded late order works.
- [ ] Real sandbox order, capture, tracking signal, and refund shown with PayPal ids.
- [ ] Every failure path F1, F5, F6, F8 demonstrated or tested; F8 shown in tests.
- [ ] Audit verify passes; tamper test fails verification as expected.
- [ ] Honest-claims checklist (10.2) fully ticked.
- [ ] Public repo, OSS license (Apache-2.0 recommended), README with limitations, `.env.example`, gitleaks CI clean, judge guide, `docs/mcp.md`.
- [ ] YouTube video <3:00, captioned, no music/logos, backup recording exists.
- [ ] Devpost rules re-read: video visibility, license wording, sponsor prize selection, edit-after-submit, eligibility, AI-disclosure.
- [ ] Return URL into our server tested (A2) and refund PENDING behavior at least documented.
- [ ] Code freeze 11-09; submit 11-10; logged-out click-through of every link.

**Should**: usability sessions summarized; AG Grid views; LLM validity number reported; DB/host survives to 12-21 or reseed TODO dated.

**Kill/cut triggers (H)**: any P1 feature not stable by 11-03 is cut; if the hosted demo is unstable by 11-05, fall back to fewer deployed units per D5.

## 14. Risk register (top 10)
| # | Risk | L | I | Mitigation |
|---|---|---|---|---|
| 1 | Live demo breaks (real approval click, return URL untested, token expiry) | M | High | Test return URL by 10-31; seeded states; reset script; token refresh; backup video recorded from live sandbox calls |
| 2 | Free-tier sleep, hours, or DB expiry kills demo before 12-21 | M-H | High | D5 decision; non-expiring Postgres or dated reseed; keep-warm pinger; smoke cron |
| 3 | Judges read it as another shopping agent | M | High | Protection is hero; agent <=25% runtime; opening line about post-purchase |
| 4 | "PayPal already has Buyer Protection" objection | M | Med | Position as proactive, pre-authorized layer on top; never claim to replace; do not mention coverage we cannot verify |
| 5 | Simulated carrier looks like a mockup | M | Med | Labels everywhere; show real PayPal calls and ids; honest limits slide |
| 6 | AI looks decorative | M | High | Show cart validity result, triage enum + confidence, drafts, brief, and fail-closed paths on screen |
| 7 | Overclaiming (legal, PayPal-backed, lift) | L-M | High | Claims checklist as release gate; copy review before video freeze |
| 8 | Scope/service sprawl (11 slugs) in 33 days | M | High | P0 cut line; P1 cut trigger 11-03; D5 |
| 9 | Prompt injection or LLM misbehavior moves money | L | High | AI has no creds and no money path; amounts from policy only; regex gate; tests with hostile text |
| 10 | Deadline/eligibility surprise (timezone conflict, India-based account, rules unread) | L-M | High | Fetch Devpost rules by 10-20; trust Devpost timer; submit 11-10 |
Also tracked: refund unknown/duplicate on concurrent clicks (mitigated by Request-Id and reconcile, V), LLM spend overrun (hard cap), secrets leak in public repo (gitleaks).

## 15. Glossary
- **Mandate**: buyer-signed, immutable terms: allowlist, max total, intent, expiry, protection terms; revocable.
- **Protection terms**: pre-authorized remedy, e.g. auto-refund up to X if not delivered by day Y (demo values, illustrative).
- **SafePayAI loop**: detect late/lost, triage, policy, checks, refund, audit.
- **Bounded agent**: LLM that only proposes catalog item IDs + quantities; cannot pay or refund.
- **Hard block**: deterministic rejection that no AI note can override.
- **Advisory intent-fit**: AI check that can only tighten.
- **Triage**: AI classification into the enum plus confidence; never decides money.
- **Fail closed**: on uncertainty, route to HUMAN_REVIEW or block.
- **Proposal hash**: hash binding an approval link to exactly one offer.
- **Demo clock**: controllable time offset used by tracking.
- **SIMULATED CARRIER**: shipment status held in our DB; PayPal tracker cannot hold late/lost/delivered (V).
- **Protected until day X**: demo window, not PayPal's real window.
- **PayPal-Request-Id**: idempotency key; replay returns the original result (V).
- **Reconcile**: resolve unknown refund outcome by lookup instead of retry.
- **Audit chain**: append-only hash-chained log; tamper-evident, not tamper-proof.
- **Outbox**: local table of events pending delivery to subscribers.
- **MCP server**: our own tool surface over verified PayPal REST calls, hosted in paypal-adapter.
- **INR**: item not received.
- **Services**: api-gateway, mandate, catalog, shopping-agent, checkout, paypal-adapter, tracking, resolution, triage-ai, audit, web.
