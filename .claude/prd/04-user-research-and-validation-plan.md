# 04 - User Research and Validation Plan (SafePayAI)

Labels: V verified, VC vendor claim, I inference/unverified. All thresholds below are **our own heuristics (H)**, not industry facts. n is tiny: results are directional, never statistical. No real users exist yet; personas are **hypotheses (I)** built only from the brief.

## 1. Personas (hypotheses, grounded in brief facts)

### P1 Buyer: "Cautious online buyer"
- Context: buys online, uses PayPal; tracking in PayPal app is separate from the web-only Resolution Center (V); item-not-received claims are manual, ~14 days average (VC/I).
- Goals: know what they are covered for before paying; not chase a refund if the order is late.
- Pains: no proactive late alerts or auto-refunds found (I); consumers over-assume protection (UK Which?, V, UK only).
- Attitude to agents: vendor surveys 19% trust AI for everyday purchases, 53-71% want approval, 60% would quit after one mistake (all VC). Treat as prompts to test, not facts.
- Needs from us: readable mandate, explicit approval click, a receipt that says what is protected and until when (demo window, not PayPal's).

### P2 Small merchant: "Policy-bound seller"
- Context: ~90% of merchants see refund/policy abuse as significant, 65% review manually (VC). Single shared sandbox merchant login in demo (V).
- Goals: refunds only inside rules they set; humans handle odd cases.
- Pains: dispute fee $15, chargeback $20 (V); seller proof of delivery can defeat buyers (V).
- Needs from us: policy they can predict (refund cap ~$50, category exclusions, velocity >2 refunds/30 days -> human; illustrative), clear reason when a case goes to human review.

### P3 Delegation-wary power buyer
- Context: comfortable with tech, distrusts autonomous spending; wants approval (53-71% VC) and hard limits.
- Goals: hard cap, allowlist, revoke anytime, see why the agent proposed a cart.
- Pains: one mistake ends trust (60% VC). Suspicious of "AI decides refund".
- Needs from us: proof AI never decides money, audit log + verify chain, fresh approval for anything outside the mandate.

## 2. Top trust moments (what we test)
| # | Moment | Risk if it fails |
|---|--------|------------------|
| T1 | Reading and signing the Mandate | Signs without understanding caps/terms |
| T2 | Seeing the agent's cart vs mandate checks | Thinks agent can overspend |
| T3 | PayPal approval click (real click in sandbox, V) | Confusion about who charges what |
| T4 | Receipt: "Protected until day X" (demo, not PayPal's real window) | Over-assumes real-world protection |
| T5 | Late/lost detected, refund offer inside terms | Surprise or "who decided this?" |
| T6 | Human-review/escalation message | Feels accused or stonewalled |
| T7 | Out-of-terms offer needing fresh approval link | Fatigue, or blind-click |
| T8 | Merchant sees policy outcome | Cannot predict or explain decisions |

## 3. Validation plan (one person, ~33 days, free)
Total target: **8-10 sessions of 15-25 min** (remote or in person), plus 2-3 async merchant-policy responses. Use a clickable build or screenshots of the real sandbox UI (labelled SIMULATED CARRIER / sandbox). Think-aloud, no coaching. Same participant may do tests A+B+C in one session; D is a separate short block; E is merchant-only.

Mix target (H): 5-6 buyer-types (incl. 2-3 delegation-wary), 2-3 merchant/seller-types. Include at least 1 participant using assistive tech or large text if reachable (accessibility check).

### Test A: Mandate screen click-through (T1, T2)
Task scenario: "You want a birthday gift for a runner under $60. Set up what the helper may do." Observe where they look, hesitate, edit.
Script (read aloud, neutral):
1. "In your own words, what does this screen let the helper do?"
2. "What is the most it can spend? How do you know?"
3. "Which shops can it use?"
4. "How would you stop it? Show me."
5. "What happens if it finds something over the limit?"
6. "What would make you not click Sign?"
7. "What is unclear or missing?"
Metrics: unaided correct answers on cap, merchants, revoke; time to sign; hesitations.
H thresholds: PASS >=80% correct on cap + allowlist + revoke across participants, 0 participants who think the agent can exceed cap. FAIL if <60% or any "it can pay anything" misread -> rewrite screen before next round.

### Test B: Plain-language mandate and receipt comprehension (T1, T4)
Show the plain-language mandate summary, later the receipt. Ask after covering the page.
1. "What are you agreeing to? Say it back."
2. "If the order never arrives, what happens?"
3. "Until when are you protected?"
4. "Is this PayPal's own buyer protection? Why/why not?"
5. "Who pays the refund?"
6. "What would you do if the package is late on day X?"
7. "Which words were confusing?"
Measure: statement-level recall (cap, window, refund trigger, "demo window, merchant-funded").
H: PASS >=75% correct on window + "not PayPal's real window" + who pays; FAIL if >=3 of 8 believe it is PayPal-backed (this is a claim we must not create).

### Test C: Consent / approval-comfort test (T2, T3, T7)
Show cart proposal with checks, then PayPal approval step, then an out-of-terms offer link.
1. "Would you approve this cart? What would you check first?"
2. "Did you feel in control at the PayPal click? Why?"
3. "If the helper had bought without asking, how would you feel?" (compare)
4. "Here is a new offer outside what you pre-agreed. What does approving it do?"
5. "Rate comfort 1-5 for: agent proposing, you approving, auto-refund inside terms."
6. "What would make you stop using this after one mistake?"
7. "What do you want to be told, and when?"
Measure: comfort ratings, whether they can state what the single-use link approves.
H: PASS median comfort >=4 for approval-gated flow and >=3 for auto-refund-inside-terms; FAIL if most say they would not delegate even with limits -> reposition copy toward "you approve everything outside terms".

### Test D: Escalation messaging (T5, T6)
Show 3 variants of human-review text (neutral vs. cold vs. over-apologetic). Randomise order.
1. "What do you think happened to your request?"
2. "What happens next, and by when?"
3. "Does any wording sound like you did something wrong?" (point to it)
4. "Who made the decision here, a person or software?"
5. "What would you do now?"
6. "Which version would you want to receive? Why?"
H: PASS 0 participants read accusation; >=80% state next step; FAIL if >=2 feel accused.

### Test E: Merchant policy comprehension (T8) - 2-3 merchant-types
Show the 3 illustrative policies and 4 case cards (inside cap, over cap, excluded category, 3rd refund in 30 days).
1. "Predict the outcome for each case before I show you."
2. "Why do you think case 4 went to a human?"
3. "Is the cap/exclusion what you'd expect? What's missing?"
4. "What would you need to trust an automatic refund?"
5. "Who should be able to override, and how?" (override = new buyer-approved offer)
6. "What would you be worried about?"
H: PASS >=3 of 4 cases predicted correctly per participant on average; FAIL if the override flow is misunderstood as direct refund.

## 4. Recruiting for free
- Friends/family-of-friends who shop online (screen: bought online in last 3 months; PayPal use optional).
- Hackathon Discord/Slack, Devpost teammate channels, r/SideProject-style communities (follow each community's rules), university groups, X/LinkedIn posts.
- Merchants: small Etsy/Shopify sellers reachable via personal network or community forums; ask for 15 min, no incentives needed or offer a thank-you/early credit.
- Screener (3 questions): online shopping frequency; used any delegation/auto-pay feature; attitude to AI buying (Likert). Deliberately seek 2-3 sceptics to avoid confirmation bias.
- Consent: say up front it is a sandbox prototype, no real money, notes anonymised; offer opt-out of recording.

## 5. Recording findings (cheap)
- One spreadsheet/markdown table per session: ID (P01..), persona type, test, task, pass/fail per question, verbatim quote, severity (1 blocker, 2 major, 3 minor), screen/element.
- Audio or screen recording only with consent; otherwise typed notes. Store locally; delete raw recordings after synthesis. No names, emails, or payment data in repo (repo is public).
- After each 3 sessions: affinity-cluster issues, count participants per issue (e.g. "4/6 misread cap").
- Keep a decisions log: finding -> change -> retest result.

## 6. Feeding findings into design
| Finding type | Decision rule (H) |
|--------------|-------------------|
| Severity 1 seen by >=2 participants | Fix before next session; retest on next 2 participants |
| Severity 2 seen by >=3 | Fix this week; log |
| Severity 3 or single mention | Backlog; fix only if cheap |
| Misread implies a forbidden claim (PayPal-backed, legally binding, real window) | Rewrite copy immediately; add on-screen sandbox/demo label |
| Participants distrust AI deciding money | Make "AI never decides money; rules do" visible near the refund offer |
| Escalation text read as accusatory | Switch to neutral template; retest |
Findings also go into the demo video narrative (what users understood), phrased honestly as "N informal sessions", never as validation of market demand.

## 7. Ethics
- Sandbox only; no real money, cards, or real PayPal credentials from participants. Participants never enter personal payment data; we use pre-made sandbox buyer.
- Label simulated parts on screen (SIMULATED CARRIER, seeded catalog, demo window).
- Voluntary, informed, can stop any time; no deception about what is real.
- Anonymise quotes; do not publish identifiable data in the public repo.
- Report negative results; do not cherry-pick; state small n.
- Inclusive recruiting where feasible; accessibility notes recorded.

## 8. Calendar (4 weeks, Oct 10 - Nov 10; mapped to sprint weeks)
| Week | Dates | Build focus (assumed) | Research |
|------|-------|-----------------------|----------|
| W1 | Oct 10-16 | Mandate, cart, checks | Write scripts, screener, consent; recruit; paper/screenshot test A with 2 pilots (fix script) |
| W2 | Oct 17-23 | Order/capture, receipt | Test A+B on 3-4 participants; fix mandate copy and receipt wording |
| W3 | Oct 24-30 | Tracking, triage, policy, refund | Test C + D on 3-4 participants; Test E async with 2-3 merchants; fix escalation wording |
| W4 | Oct 31-Nov 10 | Polish, audit log, video, submit | Retest changed screens with 2-3 people (quick A/B recheck); summarise findings; finalise copy before video freeze (~Nov 5); submit Nov 10 |
Note: official deadline Nov 12 noon PT (VC, re-read Devpost rules); keep two spare days.

## 9. Usability checklist (pass/fail per item; evaluate by self-review + tests)

### Buyer approval screen (cart / PayPal handoff / out-of-terms link)
- [ ] States merchant, items, quantity, total and currency, derived server-side, matching what PayPal will show.
- [ ] Shows which mandate this fits and the remaining cap.
- [ ] Shows hard-check results in plain words; advisory AI note is labelled "advisory".
- [ ] Single clear primary action; decline/edit equally reachable.
- [ ] Explains the PayPal redirect before it happens ("You will approve in PayPal sandbox").
- [ ] Out-of-terms link says exactly what it approves, is single-use, and shows expiry.
- [ ] Keyboard operable, visible focus, labels for screen readers, sufficient contrast, readable at 200% zoom.

### Mandate signing screen
- [ ] Plain-language summary first; technical hash/HMAC in "details".
- [ ] Cap, allowlist, expiry, intent text, protection terms each visible without scrolling or in one labelled list.
- [ ] Revoke path visible after signing.
- [ ] No claim of "legally binding", "PayPal-backed", or "non-repudiable"; sandbox/demo label present.
- [ ] Amounts shown in major units with currency; internal integers never exposed.
- [ ] Sign action requires explicit confirmation; errors say what to fix.

### Receipt
- [ ] Shows what was bought, total, mandate reference, reasons for approval.
- [ ] "Protected until day X" labelled as demo window, not PayPal's real window.
- [ ] States refund is merchant-funded via PayPal refund; SIMULATED CARRIER labelled.
- [ ] Next steps: what happens if late/lost and how to report a problem.
- [ ] Printable/readable on mobile; accessible structure.

### Human-review / escalation messaging
- [ ] Neutral, never accusatory: describe the process ("your request needs a person to look at it"), not the buyer ("suspicious", "abuse", "too many refunds").
- [ ] Do not expose velocity or risk reasoning to the buyer in judgmental terms; use "a policy limit was reached".
- [ ] States what happens next and an expected timeframe (demo: illustrative).
- [ ] Says a person, not the AI, makes the final decision; AI only summarises.
- [ ] No URLs or amounts in AI-drafted text (regex gate); no blame or apology overload.
- [ ] Offers a way to add information.
- Example neutral wording (draft): "We have received your report. Your request needs a team member to review it, so we have passed it on. We will update you here. You can add details at any time."
- Words to avoid: "flagged", "suspicious", "fraud", "denied because you", "abuse", "violation".

## 10. Open items
- Participant count may be limited by recruiting; if <8, merge A+B+C into one session and weight sceptic participants.
- Need decision from design agent on which screens exist as clickable vs. screenshots by W1 end.
- Thresholds are H and should be revisited after pilots.
