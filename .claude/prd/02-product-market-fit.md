# 02 - Product-Market Fit Analysis: SafePayAI

Labels: **V** verified, **VC** vendor/secondary claim, **I** inference/assumption. Date 2026-10-10. No invented numbers; every figure in "illustrative" blocks is a placeholder, not a forecast.

## 0. One-page answer

- SafePayAI is buyer-signed purchase protection: a Mandate pre-authorizes what an agent may buy and what is refunded if it does not arrive; a deterministic loop detects late/lost orders and refunds under those terms.
- PMF is evaluated three ways because they have different bars:
  - **Hackathon product**: PMF = "judges instantly understand a real problem and see it solved end-to-end." Achievable. Strongest of the three.
  - **Feature PayPal would ship**: PMF = moves a metric PayPal owns without raising abuse/loss. Plausible but unproven; the hackathon cannot prove it.
  - **Standalone business**: weakest. Distribution, merchant consent, and funding the refund are all owned by PayPal/merchants, not us. Not recommended as a company.
- Honest verdict (I): strong hackathon fit, credible "feature pitch", poor standalone venture.
- What we are deprioritizing: the generic shopping agent as hero, real carrier data, real money, merchant-side dashboards, multi-PSP support.

## 1. Segments and jobs-to-be-done

| Segment | Who (specific) | Job they hire it for | Pain today | Evidence |
|---|---|---|---|---|
| S1 Buyer, high-anxiety online purchase | US consumer buying from small/unknown merchants, gifts with a date | "Make sure that if this does not arrive by the date I need, I get my money back without a fight" | Item-not-received claim is manual, web-only Resolution Center, ~14 days avg (VC/I); no proactive delay alert or auto-refund found (I, absence of evidence) | Which? UK: consumers over-assume protection (V, UK only); no US awareness data (unknown) |
| S2 Buyer delegating to an agent | Early adopters letting an assistant shop | "Let the agent act but cap what it can do, and keep me protected" | Trust: 19% trust AI for everyday purchases; 60% quit after one mistake; 53-71% want approval (all VC) | ChatGPT Instant Checkout scaled back Mar 2026 (V) |
| S3 Small/mid merchant | Sells via PayPal checkout, handles own support | "Resolve a late order cheaply before it becomes a dispute, on my terms" | Dispute $15, chargeback $20 fees (V); ~90% see refund/policy abuse as significant, 65% review manually (VC) | Merchant-side tools (Narvar/Loop/AfterShip) exist but are not buyer-signed (V) |
| S4 PayPal product/risk owner | PM for disputes, checkout, agentic | "Improve branded-checkout trust and cut disputes without adding loss" | Branded checkout +2% cn two quarters; Apple Pay overtook at checkout; FY2025 transaction losses ~$1.3B +20%, cause split unknown (V) | Mgmt: agentic revenue meaningful ~2028 (V) |

- Beachhead (I): S1 + S3 pair on a single flow (buyer with a protected order, small merchant that pre-agrees terms). S2 is the demo hook, not the market.
- Why not S2 first: trust data is vendor-sourced and the largest agentic-checkout attempt retreated (V); hero must be protection, not shopping.

## 2. Value proposition canvas

**Buyer (S1/S2)**
- Gains sought: certainty on a date, no claim form, plain reasons for every decision, undo/revoke.
- Pains: filing and waiting, proving non-delivery, not knowing what is covered, fear the agent overspends.
- Pain relievers: Mandate fixes allowlist, cap, expiry; automatic detection of late/lost; refund offer inside pre-authorized terms; anything outside terms needs fresh signed approval.
- Gain creators: receipt with reasons; hash-chained audit log with "verify chain".

**Merchant (S3)**
- Gains sought: fewer disputes, fewer manual reviews, keep customer.
- Pains: abuse/velocity, $15/$20 fees (V), manual triage.
- Relievers: deterministic merchant policy (cap, category exclusions, velocity -> human); AI only classifies and drafts, never decides money; merchant override is a new buyer-approved offer.

**Core value proposition (testable)**: "If a protected order is late or lost, the buyer is offered a refund under terms they signed at purchase, with no claim form." Test: median time from problem signal to buyer-visible resolution.

## 3. The metric PayPal owns that this moves

| Metric | Why PayPal cares | How SafePayAI moves it | Status |
|---|---|---|---|
| Time from problem signal to buyer resolution | Drives buyer trust at checkout; today ~14 days for INR claims (VC/I) | Detect from tracking/clock, offer pre-authorized refund immediately | Demo shows minutes; production number unknown |
| Disputes per order | Each costs $15 (V) and can become a $20 chargeback (V) | Resolve before escalation | Unknown; needs pilot |
| Branded-checkout conversion/trust | Filing priority "restore branded checkout momentum" (V) | Visible "protected until..." promise at checkout (I) | Unknown; conversion lift NOT claimed |
| Transaction losses | ~$1.3B FY2025 +20%, split unknown (V) | Neutral-to-risky: refunds are merchant-funded; abuse is the risk | Must be shown not to increase |

- Caveat: "Protected until day X" in the demo is our window, NOT PayPal's real protection window (V by design).
- Caveat: PayPal tracker API cannot represent late/lost/delivered (V, our spike); real carrier feed integration is required for production (I).

## 4. Unit economics framing (only verified fees; scenarios illustrative)

Verified inputs (V): dispute fee $15; chargeback fee $20; Mastercard average chargeback cost $128 (card-network figure, not PayPal-specific; includes costs beyond the fee).
Unknown (do not guess): problem-order rate, share of problems that become disputes, refund rate, cost of a manual claim to PayPal, abuse rate, price PayPal would accept.

Parameterised model (per 1,000 protected orders):
- P = problem orders (late/lost). **Unknown.**
- E = share of P that would have escalated to a dispute without SafePayAI. **Unknown.**
- A = share of automatic refunds that are abusive/undeserved. **Unknown; main downside.**
- Avoided dispute cost = P x E x $15 (add $20 for the share that would reach chargeback).
- Added refund cost = P x (1 - E) x avg refund x ... only if those buyers previously did not claim. Refunds the buyer never would have claimed are a pure cost to the merchant.
- Key insight (I): savings come only from problems that WOULD have escalated; auto-refunding silent buyers is net cost. This is the real economic risk.

Illustrative scenarios (round numbers chosen for arithmetic only, not estimates of reality):
| Scenario | Assumed P | Assumed E | Dispute fees avoided at $15 | Reading |
|---|---|---|---|---|
| Low | 10 | 20% | 2 x $15 = $30 | Fees alone are tiny; value must come from trust/conversion or chargeback avoidance |
| Mid | 20 | 50% | 10 x $15 = $150 | Still small vs. refunds paid out |
| High | 20 | 80% | 16 x $15 = $240 (+ $20 x any chargebacks; $128 network cost if chargebacks occur) | Only here does the fee math start to matter |

- Takeaway (I): the $15 fee alone does not justify the product. The case rests on (a) chargeback avoidance ($20 / $128), (b) buyer trust at branded checkout, (c) support-cost reduction. All three need real data.
- Merchant sees it as insurance they self-fund; they accept only if abuse is bounded by their policy caps.

## 5. Adoption barriers

| Barrier | Why it blocks | Mitigation in design | Residual risk |
|---|---|---|---|
| Merchant consent | Merchant funds refunds; will not accept open-ended liability | Terms pre-agreed with cap and category exclusions; deterministic policy; override = new offer | Real merchants not tested; demo uses 3 virtual merchants on one sandbox login |
| Abuse / friendly fraud | Buyers can claim late when not (VC: ~90% merchants worried) | Velocity rule (>2 refunds/30 days -> human); cap ~$50; reviewer brief; hash-chained audit | Caps and thresholds are illustrative, not tuned |
| Trust in AI | 19% trust; 60% quit after one mistake (VC) | AI never decides money; fail-closed to HUMAN_REVIEW; reasons shown | Perception risk even if architecture is safe |
| Data truth | Late/lost needs real carrier data | Simulated carrier in demo, labelled | Largest production gap |
| Legal/regulatory | Buyer-signed terms vs. existing protection programs | No claim of legally binding or compliant | Unknown; needs counsel |
| Cannibalizing PayPal Purchase Protection | Feature overlaps existing program | Position as faster layer on top (I) | PayPal policy owners may object |

## 6. Pricing and strategic angles

- Hackathon: free, open source. No pricing claims.
- PayPal feature (I, options only):
  - Included as checkout trust feature (cost-center, conversion argument).
  - Merchant opt-in with a small fee (needs data on dispute savings; unknown).
  - Bundle with agentic checkout: "agent purchases are mandate-bound and protected by default".
- Standalone (I): a per-protected-order fee layered on PayPal would depend on PayPal's APIs and policy, with PayPal able to build the same thing. Dependency risk is structural; no moat beyond execution speed.
- Strategic angle for judges and PMs: SafePayAI is a safety layer that makes agentic commerce adoptable, matching PayPal's stated agentic timeline (V) rather than another shopping agent.

## 7. Evidence that would prove PMF vs. what the hackathon can prove

**Would prove PMF (production-grade)**
- Buyer: protected orders have higher repeat/conversion than unprotected, in a controlled test.
- Buyer: median time to resolution drops vs. manual claims baseline.
- Merchant: opt-in rate with real caps; dispute rate lower on protected orders.
- Abuse: refund-per-protected-order and abuse rate within merchant tolerance.
- PayPal: loss rate not increased; unit economics positive after refunds.

**Hackathon CAN show**
- End-to-end working flow in sandbox: mandate -> cart -> approve -> capture -> late -> triage -> refund -> audit.
- Safety design: AI cannot move money; deterministic checks; idempotent refunds (V from spike).
- Clear problem narrative with labelled vendor evidence.

**Hackathon CANNOT show**
- Real buyer demand or willingness to sign a Mandate (zero users).
- Real merchant consent or realistic abuse rates.
- Real carrier data, real money, real PayPal protection coverage.
- Conversion lift, dispute reduction, or loss impact. Do not claim any.
- LLM cart reliability in the wild (target >=95% valid on 20-prompt test is a goal, not yet measured, I).

Cheap evidence we could add before submission (I): 5-8 buyer interviews on "would you sign this at checkout"; 2-3 merchant conversations on cap/terms; both labelled as small, qualitative.

## 8. Top 5 reasons a PayPal PM would still say no, with answers

| # | Objection | Honest answer |
|---|---|---|
| 1 | "Auto-refunds invite abuse and raise our losses." | Refunds are inside buyer-signed, merchant-agreed caps; velocity rule routes to humans; AI cannot set amounts. Honest gap: thresholds are untuned and abuse rate is unknown; a pilot with tight caps would measure it. |
| 2 | "We already have Purchase Protection / Resolution Center." | SafePayAI is a faster, proactive layer, not a replacement: it acts on signal rather than waiting for a claim. Honest gap: overlap and policy conflicts need PayPal policy owners; our "protected until" window is not PayPal's. |
| 3 | "You can't detect late/lost; our tracker API doesn't support it." | Correct: our spike showed PATCH only supports CANCELLED (V). Production would need carrier feeds; the demo simulates and labels it. This is the biggest technical dependency, stated openly. |
| 4 | "Merchants won't opt in to pre-agreed refunds." | Plausible. Answer: caps and exclusions let them bound liability and dispute fees ($15/$20, V) are real; but no merchant evidence exists. Needs a design-partner test. |
| 5 | "Consumers won't use or trust an AI agent buying for them." | The hero is protection, not shopping; the agent only proposes carts inside a Mandate and the human approves in PayPal. Vendor data on trust is poor (VC), so the mandate/approval design is the answer, not a claim of demand. |

Runner-up objections (not in top 5): sandbox-only proof, hash-chain is demo-grade not buyer-held key, single shared merchant login, cost/effort to maintain vs. ~$1.5B cost-cutting focus (V context).

## 9. Open questions

- Official Devpost rules re-read (deadline VC).
- US awareness of PayPal protection: unknown.
- Share of PayPal transaction losses attributable to INR/late: unknown.
- Whether PayPal Disputes API is usable with our scopes: untested.
