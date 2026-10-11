# 03 - Hackathon Win Probability (calibrated)

Labels: **V** verified, **VC** secondary claim, **I** inference. All probabilities below are SUBJECTIVE estimates with wide ranges. Unknowns: number of entries, exact weights, judge identities, field quality. Treat bands as ordering, not forecasts.

## 0. Summary

- Overall verdict: strong entry in a likely-crowded field; realistic chance at a category prize, lower chance at a top-3 overall.
- Best-fit awards: Best Use of PayPal+AI, Most Impactful, Agentic Commerce. Weaker fit: Most Creative.
- Biggest controllable risks: demo reliability (sandbox needs a real buyer click), AI role looking decorative, video quality.
- Biggest uncontrollable risks: field size, judge taste, ties to saturated ideas.

## 1. Scoring vs. the 5 criteria (weights unstated; 1-5, self-assessed, assumes plan is executed)

| Criterion | Score | Why | What would lower it |
|---|---|---|---|
| Technological implementation | 4 | Verified Orders v2, capture, tracking, partial refunds, idempotency, 409 handling (V from spike); microservices + own MCP over REST; hash-chained audit | Flaky demo, over-engineering that fails live, untested return URL/webhooks |
| Design (complete, coherent product) | 4 | One clear loop from mandate to refund; reasons on receipts; labelled simulations | Too many services/screens; UI polish gap; confusing states (12 states) |
| Potential impact | 3.5 | Real pain (INR claims slow, manual; VC/I) tied to PayPal metrics; honest about unproven economics | Judges may see sandbox-only; impact unproven (cannot prove PMF, see doc 02) |
| Innovation | 3.5 | "Buyer-signed mandate + deterministic refund, AI cannot move money" is distinct from shopping agents; each part is individually known | Seen as "guardrails + refund bot"; agent portion looks generic |
| Presentation | 3.5 to 4 | Depends on <3 min video and README; honest framing is a differentiator | Dense video, too much narration, no clear opening problem |

- Aggregate self-score ~3.7 of 5 (I). Self-scores are optimistic by default; discount by ~0.5 for calibration, giving ~3.2-3.7 as an external-judge expectation (I).

## 2. Award likelihood (subjective, wide)

| Award | Band | Rough range (subjective) | Reasoning |
|---|---|---|---|
| Overall top 3 | Low-Medium | 5-20% | Winners last year were practical, demoable agent/payment projects (V); we fit the type, but field size unknown and top-3 is scarce |
| Best Use of PayPal + AI | Medium | 15-35% | PayPal central across Orders, tracking, refunds; AI has real but bounded role; risk: "AI is only advisory" read as shallow |
| Best Use of Agentic Commerce | Medium | 15-30% | Bounded shopping agent + own MCP + mandate fits; but ~25% of demo only, and agentic is the most contested category (I) |
| Most Impactful | Medium | 15-30% | Clear real-world pain; weakened by sandbox-only and no user evidence |
| Most Creative | Low | 3-12% | Strong concept but not visually/conceptually flashy |
| Best Demo Delivery | Low-Medium | 8-20% | Depends almost fully on video quality and zero live failures |
| Render sponsor prize | Medium | 10-30% | Only if hosted on Render with a clear usage story (verify eligibility, I); one sponsor prize per project |
| AG Grid sponsor prize | Low-Medium | 5-20% | Only if the audit log/reviewer queue is a real AG Grid use; cannot do both Render and AG Grid for a prize (V rule: one sponsor prize) |

- These do not sum or add: awards overlap and a project may win several non-sponsor categories only if rules allow (verify, I).
- Any chance at all of winning at least one prize: Medium (roughly 25-50%, subjective). The wide band reflects unknown prize count and field.

## 3. Competitor-field assumptions (I)

- Likely entries: generic shopping agents, price-tracker auto-buyers, spend-limit dashboards, chat invoicing, x402 wrappers (saturated, I).
- Likely strong competitors: polished invoice/subscription/payouts tools with PayPal APIs, MCP integrations, fraud/dispute assistants, small-business finance copilots.
- Many entries will be mockups or shallow API wrappers; rules require working demo, so a real end-to-end loop is a separation advantage.
- Saturation risk: "agent that buys things with spend limit" is the most crowded idea; our hero (protection after purchase) avoids it but our agent segment overlaps. Keep it subordinate.
- Dispute/refund-focused entries probably exist (I); differentiation = pre-authorized mandate, AI-cannot-move-money, audit proof, idempotent refund handling.
- Field size: unknown. A typical large hackathon may have hundreds of submissions (I); do not rely on it.

## 4. The 10 factors that move the odds

| # | Factor | Direction | What we do |
|---|---|---|---|
| 1 | Demo reliability (sandbox buyer click, refund call) | Largest swing | Pre-recorded fallback clips; seeded state; reset script; US personal sandbox buyer (V worked); test return URL early (untested) |
| 2 | Honesty / labelling | Positive with PayPal engineers | Keep SIMULATED CARRIER labels, "sandbox only", no overclaims (rules in brief) |
| 3 | AI role realness | Large | Show LLM cart, triage classification, drafts, reviewer brief with measured results (e.g., cart validity on 20 prompts); explain fail-closed |
| 4 | Video quality (<3 min) | Large | 3-act script: problem (15s), mandate+agent (45s), late order -> refund (80s), safety/audit (30s); captions; no music/logos |
| 5 | Polish / UX coherence | Medium-Large | Fewer screens, one timeline view, clear state badge; consistent copy |
| 6 | Scope discipline | Medium | Cut anything not on the demo path; 12 states shown as 5 key ones in video |
| 7 | PayPal depth | Medium-Large | Show Orders, capture, tracking, refund, Request-Id idempotency, reconcile on 409 (all V); own MCP server |
| 8 | Narrative clarity | Medium-Large | Opening line tied to PayPal metrics (time to resolution, disputes) without inventing numbers |
| 9 | Repo/readme/run instructions | Medium | Public repo, OSS license, .env.example, gitleaks, one-command run, hosted demo |
| 10 | Submission mechanics | Binary | Submit 2026-11-10 (2 days early); re-read Devpost rules; check eligibility (India-based account noted, I) |

## 5. Scenarios

| Scenario | Probability (subjective) | What happens | Outcome |
|---|---|---|---|
| Pessimistic | ~30-40% | Demo glitch or weak video; field has polished agent demos; judges see "guardrails" as safe-but-boring | No prize, or possibly honorable mention |
| Base | ~40-50% | Solid working entry, clear video; wins nothing top-tier but competitive; possible one category/sponsor prize | 0-1 prizes |
| Optimistic | ~10-20% | Flawless demo, memorable "refund appears on its own" moment, judges value safety framing | Category prize plus top-3 contention |

- Probabilities are judgement; ranges deliberately overlap.

## 6. Leading indicators (check weekly through 2026-11-10)

- Spike checklist closed: return URL to our server works; refund PENDING handled; hosted deploy stable.
- Cart validity >=95% on 20 prompts (target, not measured, I).
- Full demo runs 10 consecutive times without manual fix.
- Cold viewer test: 3 outsiders watch video, can state the product in one sentence.
- Video first cut <3:00 by ~2026-11-01.
- Devpost rules re-read; sponsor prize eligibility confirmed.
- Public gallery/discord signals of other entries (saturation check), if available.

## 7. Cut or double down

**Double down**
- The 60-second "late order -> automatic refund inside signed terms" moment; make it unmistakable.
- Visible AI role: triage + drafts + reviewer brief with fail-closed paths on screen.
- Safety story: AI has no credentials; idempotent refund; audit chain verify.
- Own MCP server as the agentic surface, shown briefly.
- Honest "what is simulated" slide.

**Cut / minimise**
- Shopping agent beyond a 20-30 second proposal step (generic-agent trap).
- Extra microservices that add failure points without demo value; consider fewer deployed units if free-tier sleep hurts (verify, I).
- 12-state diagram in the video; hash-chain explanation beyond 10 seconds.
- Anything requiring untested PayPal features (webhooks, Disputes API, Vault, Fastlane).
- Sponsor-prize chasing: pick ONE (likely Render if hosting there) and do not bend the product for AG Grid.

## 8. Calibration notes

- Self-assessed scores usually run high; the real risk is unknown field and judge taste.
- No evidence yet about judges' weights or actual submission count; revise after Devpost rules and any gallery visibility.
- Revisit this doc after the first full end-to-end run (target mid-October) and again after video first cut.
