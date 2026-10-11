# 01 - Market Study (SafePayAI) - as of 2026-10-10

Labels: **V** verified (primary or our spike), **VC** vendor/secondary claim, **I** inference. No market-size (TAM) figure is cited: **TAM/SAM for buyer-signed post-purchase protection = unknown**. Items marked "(brief)" are inherited from 00-context-brief.md and not re-researched.

## 0. Update delta vs brief (re-verified this session)
- Hackathon deadline: PayPal blog says submissions close **Nov 12, 2026, no time or timezone given**; a Devpost-mirror snippet says **3:00 PM EST** (VC); brief says noon PT (VC). CONFLICT: re-read official Devpost rules; plan to submit Nov 10 regardless. (V for date, unknown for time)
- PayPal blog confirms: prize pool "over $60,000"; honorable mentions $5,000 each (Most Creative, Most Impactful, Best Demo Delivery, Best Use of PayPal + AI, Best Use of Agentic Commerce); fundamental requirement "must meaningfully use both PayPal and AI"; no tracks; **judging criteria not listed on the blog page** (V). Winners announced Dec 21, 2026 (V). Devpost mirror shows $67,500 and 2,277 participants (VC).
- ChatGPT Instant Checkout scale-back (Mar 2026) re-confirmed by multiple outlets (V-ish, secondary): only ~a dozen merchants live per Shopify president; Walmart reported Instant Checkout conversion ~3x lower than click-through to its own site; OpenAI moved checkout to merchant apps, keeps Agentic Commerce Protocol (ACP, co-developed with Stripe). Forbes-type counter-view: test lacked multi-item carts and tax remittance (VC).
- Google UCP launched Jan 11, 2026 (NRF); added Cart/Catalog/Identity Linking in Mar; Universal Cart at I/O May 19; live in AI Mode/Gemini for US retailers; works with AP2 for payment authorization (VC, mostly explainer blogs; check Google docs).
- Card networks: Visa Intelligent Commerce has 100+ partners; Mastercard Agent Pay pilots (Westpac, Axis Bank); practitioner analysis says Visa has **no agent-specific dispute reason code**, agent disputes fall under card-absent fraud; Amex committed to cover erroneous purchases by registered agents (all VC).
- x402: transferred to Linux Foundation governance by Apr 2026; cumulative transaction figures conflict (100M to 169M) and Artemis estimates ~50% artificial; CoinDesk estimate of real daily settlement ~$28k (VC, treat as unreliable).

## 1. Market definition and who pays / benefits
Definition: **post-purchase protection and resolution for online purchases made by (or via) agents, executed under buyer pre-authorized terms.** Adjacent to disputes, tracking, and agent payments; no established category name (I).

| Party | Role | Pain / benefit | Pays? |
|---|---|---|---|
| Buyer | Signs Mandate | Does not have to chase refund; bounded agent risk; refund without a 14-day manual claim (claim time VC, brief) | Not in prototype; free as feature (I) |
| Merchant | Funds refunds, sets policy | Cheaper than a dispute ($15 PayPal dispute fee, $20 chargeback fee, V brief; Mastercard avg chargeback cost $128, V brief); keeps customer; deterministic policy limits abuse | Would pay per resolved case or via checkout fee (I) |
| PayPal ("customer" of the idea) | Platform | Branded checkout is flat (+2% cn two quarters, V brief); filing priority "restoring branded checkout momentum" (V); FY2025 transaction losses ~$1.3B, +20%, cause split unknown (V); no consumer-facing AI (V); management sees agentic revenue meaningful ~2028 (V) | Would adopt if it lowers losses or lifts branded-checkout trust (I) |
| Agent/AI platforms | Distribution | Need trust layer for agent buying | Unknown |

Honest framing: PayPal is the "customer" for a **demonstration of a differentiated, trust-building agent-era feature**, not a commercial buyer today (I).

## 2. Problem evidence (labelled)
- **Post-purchase gap at PayPal**: app tracking is separate from web-only Resolution Center; item-not-received claims are manual (~14 days avg, VC/I); no auto-refund or proactive delay alert found (I, absence of evidence). (brief)
- **Dispute cost**: PayPal dispute $15, chargeback $20; Mastercard avg chargeback cost $128 (V, brief). PayPal FY2025 transaction losses ~$1.3B +20% (V, brief).
- **Seller-side asymmetry**: Seller Protection stopped covering INR chargebacks (2024, V); seller proof of delivery can defeat buyers (V). (brief)
- **Refund/policy abuse**: ~90% of merchants see it as significant; 65% review manually (VC, brief). Source not re-checked; treat as directional.
- **Pre-dispute tools exist but are merchant-governed**: Visa RDR (Verifi) auto-refunds matched pre-disputes by merchant rules; refunds are final; vendors cite 50-70% resolution on eligible disputes (VC, vendor with commercial interest: chargeback.io, Checkout.com docs).
- **Agent-commerce trust**: 19% trust AI for everyday purchases; 60% would quit after one mistake; 53-71% want approval; 54% would use AI for delivery monitoring/resolution (all VC surveys, brief). UK Which?: consumers over-assume protection (V, UK only). US awareness of PayPal protection: unknown.
- **Network-level gap for agent disputes**: no agent-specific Visa reason code; post-transaction/liability infrastructure "largely unaddressed" per Chargebacks911 (VC, vendor with interest).

## 3. Competitive landscape
ACTS = moves money or changes order state on buyer's behalf; DISPLAYS = informs only.

| Player | After purchase | ACTS / DISPLAYS | Evidence |
|---|---|---|---|
| PayPal (today) | Tracking in app; Resolution Center claim, manual; Buyer Protection by claim | Mostly DISPLAYS; refund only after claim/merchant | brief; agent ready promises "buyer protection, dispute resolution" for agent purchases at launch Oct 2025 (VC; terms for agent purchases not verified) |
| Apple / Google Wallet | Order tracking | DISPLAYS | V brief |
| Shop app (Shopify) | Package tracking; returns handling unverified | DISPLAYS | V brief |
| Klarna / Affirm | Refund waits for merchant | DISPLAYS / waits | V brief |
| Amazon | A-to-z / auto refunds on own orders | ACTS, own orders only | VC brief |
| Visa RDR / Ethoca (Mastercard) | Pre-dispute alerts; merchant rule-based auto-refund | ACTS (merchant-governed, after cardholder dispute is filed) | V brief; chargeback.io, Checkout.com docs |
| Justt / Chargeflow | Post-dispute chargeback representment (card) | ACTS for merchant, against buyer claim | V brief |
| Narvar / Loop / AfterShip | Merchant-side tracking pages, returns | Mostly DISPLAYS / merchant workflows | V brief |
| Stripe | Radar, disputes, ACP co-developer, agentic suite | ACTS in fraud/dispute tooling; no buyer-signed protection | V brief |
| Google AP2 / UCP | AP2 signed mandates for authorization; UCP cart/catalog; merchant stays merchant of record | Pre-purchase authorization; post-purchase resolution not the focus (I) | VC |
| Visa Intelligent Commerce | Agent credentials/tokens, partner program | Pre-purchase/payment; disputes unaddressed (VC) | VC |
| Mastercard Agent Pay | Registered, verified agents; mechanisms for disputed agent transactions | Payment-time; dispute mechanism details unverified | VC |
| Coinbase x402 (Linux Foundation) | HTTP 402 micropayments for APIs/content | Payment-time; no buyer protection | VC; volumes unreliable |
| Intuit QuickBooks agents | Accounting automation | Out of scope | V brief |

Key observation: **mandate protocols (AP2, card networks) stop at "authorized to pay"; post-purchase tools are merchant-side or card-dispute-side.** No researched player combines buyer-signed pre-authorized refund terms with automatic delivery-failure detection (I, absence of evidence, not exhaustive).

## 4. Whitespace and why it is real or not
Whitespace (I): **buyer-signed "if it does not arrive, refund up to X by day Y" executed automatically**, applied to agent or human purchases.

Real because:
- Gap between authorization (AP2/network programs) and resolution (manual claims, chargebacks) is acknowledged by vendors (VC).
- Fits PayPal's stated problems: branded checkout trust, transaction loss, agent readiness (V).
- Merchant economics: a pre-agreed refund is cheaper than a $15-$128 dispute (V brief) if the loss rate on the delivery-failure class is meaningful (unknown).

Not (fully) real / weak points:
- Merchants must opt in to fund it; no evidence yet they would accept buyer-signed terms (I).
- PayPal may already cover this via agent ready + Buyer Protection (terms unverified); Amazon-style auto-refund shows large incumbents can do it internally.
- Delivery failure may be a small share of PayPal's $1.3B losses; split by cause unknown (V).
- Our carrier is simulated; PayPal sandbox cannot represent late/lost/delivered (V spike), so real detection is unproven.
- Demand for agent buying itself is currently soft (see 5).

## 5. Trends
Tailwinds:
- Agent protocols proliferating (ACP, UCP/AP2, Visa/Mastercard programs, x402) -> trust/post-purchase layer is the missing piece (VC/I).
- UCP live in Gemini/AI Mode for US retailers; Universal Cart (VC).
- PayPal needs differentiated checkout story; cost plan >= $1.5B with ~40% AI (V brief).
- Surveys: users want approval and would use AI for delivery monitoring (VC).

Headwinds:
- **ChatGPT Instant Checkout pullback** (Mar 2026): ~a dozen merchants live, Walmart conversion ~3x lower than click-through, checkout returned to merchants (secondary reports; Forrester, Digital Commerce 360, Adweek, TechCrunch cited by search). Reading: agents-as-checkout demand unproven; discovery works better than buying (I).
- Management expects agentic revenue meaningful only ~2028 (V).
- Saturated hackathon themes: generic shopping agents, price-tracker auto-buyers, spend dashboards, x402 wrappers (I).
- Apple Pay overtook PayPal at checkout (V brief); Rewards cash-out removed Aug 2026; Honey litigation (V brief): brand-trust issues cut both ways (a trust feature helps; consumer skepticism hurts).
- Regulatory (I, not researched): Reg E/Z, state laws, and card-network rules govern liability; a private "mandate" is not a legal instrument.

Implication: lead with protection and trust; present the agent as bounded and secondary (matches brief's ~25% of demo).

## 6. What a hackathon prototype can and cannot prove
Can prove:
- End-to-end flow in PayPal sandbox: mandate, server-priced order, approval, capture, tracking signal, partial refund with idempotency, reconciliation (V spike).
- Fail-closed AI: AI triage classifies and drafts; deterministic policy decides money; audit chain verifies.
- UX: a protected purchase where the buyer did nothing at failure time.
- Feasibility of the MCP surface over PayPal REST.

Cannot prove:
- Merchant willingness to fund, buyer willingness to sign, or any conversion/loss impact.
- Real carrier detection (simulated; PayPal tracking cannot hold delivered/late/lost, V).
- Real PayPal protection coverage or window; real disputes (Disputes API untested); webhooks; refund PENDING cases.
- Security/compliance (demo-grade HMAC, not buyer-held keys; single shared merchant login).
- Market size or ROI: unknown.
- LLM cart reliability beyond the 20-prompt target (not yet run).

## 7. Risks to the thesis
- R1: Incumbent answer: PayPal agent ready/Buyer Protection already covers it; judges may ask "how is this different". Mitigation: emphasise pre-authorized, automatic, buyer-signed terms; do not claim to replace Buyer Protection.
- R2: Judges read it as another shopping agent (saturation). Mitigation: protection is the hero; agent bounded.
- R3: Demand: agent buying weak (Instant Checkout pullback); protection also valuable for human purchases - position protocol as agent-ready, not agent-only.
- R4: Merchant incentive: why fund refunds? Mitigation: framed as dispute-cost avoidance (V fees) but merchant opt-in unvalidated.
- R5: Abuse: pre-authorized auto-refund invites false claims; mitigations in design (policy cap, velocity, human review).
- R6: Simulation optics: simulated carrier may look like mockup; label clearly, show real PayPal calls and sandbox IDs.
- R7: Claims risk: avoid "PayPal-backed/protected", legal, compliance claims (brief rules).
- R8: Sandbox constraints (India-based merchant account, buyer region, real approval click) can break the live demo; prepare recorded fallback.
- R9: Deadline timezone ambiguity.

## 8. Sources
- PayPal AI hackathon blog: https://developer.paypal.com/community/blog/PayPal_AI_Hackathon (V for dates/prizes)
- PayPal hackathon winners (prior): https://developer.paypal.com/community/blog/winners-dev-days-hackathon
- PayPal Oct 2025 agentic commerce launch: https://newsroom.paypal-corp.com/2025-10-28-PayPal-Launches-Agentic-Commerce-Services-to-Power-AI-Driven-Shopping
- Storyboard18 on OpenAI scale-back: https://storyboard18.com/digital/openai-reduces-chatgpt-shopping-focus-shifts-to-product-discovery-93192.html
- Digital Commerce 360: https://www.digitalcommerce360.com/2026/03/06/openai-shifts-checkout-plans-agentic-commerce-strategy/amp/
- Forrester (not fetched; redirected): https://www.forrester.com/blogs/what-it-means-that-the-leader-in-agentic-commerce-just-pulled-back
- EcomCrew: https://www.ecomcrew.com/openai-pulls-back-on-chatgpt-instant-checkout/
- Adweek: https://tunnel-sergio.adweek.com/commerce/openais-chatgpt-is-making-a-big-change-to-its-commerce-strategy/
- UCP explainers (VC): https://monei.com/blog/google-ucp-explained/ ; https://pimberly.com/blog/what-is-ucp/ ; https://www.datasolution.fr/en/universal-commerce-protocol-ucp-google-ushers-in-the-age-of-agentic-commerce-with-ai/
- American Banker, card networks and agentic AI: https://americanbanker.com/payments/news/visa-mastercard-expand-agentic-ai-deployments
- Agentic dispute commentary (VC): https://stellagent.ai/insights/agentic-commerce-dispute-wave ; https://current.tinyfish.ai/issue/36/practitioners-corner/article/28338/the-dispute-file-is-the-spec
- Visa RDR/Ethoca: https://www.checkout.com/docs/payments/process-disputes/pre-dispute-resolution ; https://www.chargeback.io/blog/what-is-rapid-dispute-resolution-rdr ; https://help.trustpayments.com/hc/en-us/articles/45051924661777-What-are-Verifi-and-Ethoca
- x402 (VC, unreliable volumes): https://www.valuethemarkets.com/cryptocurrency/news/coinbases-x402-protocol-reaches-100-million-transactions-in-record-time ; https://www.kucoin.com/news/flash/coinbase-processes-1t-in-stablecoin-payments-annually-x402-hits-160m-transactions
- Everything else (PayPal Q2 2026 financials, fees, survey stats, competitor display-only facts, Which? UK): inherited from /home/harsh/Projects/artiq/.claude/prd/00-context-brief.md with its labels.
