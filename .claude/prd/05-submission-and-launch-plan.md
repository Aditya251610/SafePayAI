# 05 - Submission and Launch Plan (SafePayAI)

Labels: V verified, VC vendor/secondary, I inference/unverified. Date 2026-10-10. Target submit 2026-11-10 (2 days buffer before 11-12 noon PT, VC).

## 0. What the extra search found
- PayPal community blog (V, primary): https://developer.paypal.com/community/blog/PayPal_AI_Hackathon
  - Only stated requirement: "must meaningfully use both PayPal and AI". No tracks, no rubric published.
  - Dates: submissions open Oct 1, close Nov 12, winners Dec 21, 2026.
  - Prizes "$60,000+" (blog) vs "$67,500" (Devpost listing, VC): conflict, do not cite a total.
  - Best Overall 1st $12k / 2nd $8k / 3rd $5k; honorable mentions $5k each: Most Creative, Most Impactful, Best Demo Delivery, Best Use of PayPal + AI, Best Use of Agentic Commerce.
  - Sponsor prizes: AG Grid (1st $5k, 2nd $2k, 3 x $1k), APIMatic (3 x $1k), Bryntum (3 x $1k), Channel3 ($1.5k), Render (credits: $1k / $750 / $500).
  - Blog says nothing on video, repo, license. Those come from the Devpost rules page (not fetched; see checklist).
- Winners announced Dec 21 = the demo must stay alive ~6 weeks AFTER submit (I: judging window). Drives section 5.
- No extra PayPal/Devpost submission guidance found beyond the above (I: absence of evidence in a standard search).

## 1. Devpost submission checklist
| # | Item | Source | Status |
|---|---|---|---|
| 1 | Devpost account, registered for the hackathon, team members added | Devpost | re-verify |
| 2 | PayPal central + meaningful AI | brief + blog (V) | design satisfies |
| 3 | Working demo, no mockups | brief | build |
| 4 | Public GitHub repo with OSI license visible (LICENSE at root, GitHub detects it) | brief | re-verify exact wording (e.g. "open source license" in About section) |
| 5 | Hosted demo URL OR run instructions (do both) | brief | build |
| 6 | YouTube video under 3 min, public/unlisted, linked on Devpost | brief | re-verify: public vs unlisted, "first 3 min only judged" wording, language/captions |
| 7 | Text description (Devpost story fields) | Devpost | write section 7 |
| 8 | Image gallery, thumbnail (3:2), screenshots | Devpost | make |
| 9 | "Built with" tags (python, fastapi, paypal, mcp, postgres, etc.) | Devpost | fill |
| 10 | Testing instructions / sandbox credentials for judges (buyer sandbox login, never real) | Devpost | see 1a |
| 11 | Pick ONE sponsor prize (brief: one per project) | brief | section 6; re-verify whether a form field or checkbox |
| 12 | Eligibility: age of majority, country, team size, employee conflicts, IP/ownership of code | rules | re-verify (I: coursejoiner says age of majority; secondary) |
| 13 | Submit before 11-12 noon PT; confirm deadline in the Devpost countdown, not blogs (timezone conflict seen: one source says 11-13 01:30 IST = 11-12 noon PT is NOT matching, it equals 11-12 15:00 ET; treat the Devpost timer as truth) | I | re-verify |
| 14 | After submit: open the public project page logged out and click every link | us | todo |
| 15 | Edits allowed after submit before deadline? | unknown | re-verify |
| 16 | Disclosure of AI-coding-agent use / third-party assets / pre-existing code | rules | re-verify; default: disclose openly in README |

### 1a. Judge test credentials (decision)
- Sandbox buyer is a US personal sandbox account (V: India buyer failed in USD). Publish sandbox buyer email + password in the Devpost "testing instructions" ONLY if it is a throwaway sandbox account with no link to real identity; rotate after judging.
- Never publish PAYPAL_CLIENT_ID/SECRET. Judges use our hosted app, not our keys.
- Also offer a "Demo mode" button that fakes nothing but pre-fills the approval step hint ("click Approve in the PayPal sandbox page"), since a real click is required (V).

## 2. README structure (judges read this in <2 min)
1. Title + one-line pitch + badges (license, CI) + hosted-demo link + video link (top, above the fold).
2. "30-second understanding" (3 bullets + one GIF):
   - Problem: agents/buyers pay with no pre-agreed remedy; claims are manual (I/VC).
   - Idea: buyer-signed Mandate -> bounded agent -> deterministic SafePayAI refund; AI never moves money.
   - Proof: sandbox order, late carrier (simulated), refund visible in PayPal sandbox.
3. Run it
   - Hosted: URL + judge credentials pointer.
   - One command: `docker compose up` (or `make demo`) after `cp .env.example .env` and pasting sandbox keys. Must work from a clean clone; test on a fresh machine/container (I: target).
   - Offline/no-keys mode: `DEMO_PAYPAL=recorded`? NO - mockups are disallowed; instead state keys are required and show how to get free sandbox keys (2 steps).
4. Architecture diagram placeholder: `docs/architecture.png` (+ Mermaid source in repo). Must show: gateway/auth, services, MCP server over PayPal REST, AI boundary (no credentials, no money path), audit chain, simulated carrier.
5. How PayPal is used: table of exact endpoints used (Orders v2 create/capture, track, Payments v2 refund, GET refund) - all V from spike.
6. How AI is used and bounded: cart proposal, intent-fit (can only tighten), triage enum, drafts (regex gate), reviewer brief; fail-closed.
7. Honesty / limitations section (mandatory, early not buried):
   - Sandbox only; no real money. Carrier SIMULATED; catalog SEEDED; 3 virtual merchants settle to one sandbox merchant.
   - Mandate signature is server HMAC (demo-grade), not buyer-held key; not legally binding, not non-repudiable.
   - "Protected until day X" is a demo window, not PayPal's real protection window. Refund is merchant-funded via PayPal refund.
   - Not tested: webhooks, Disputes API, PENDING refunds (state what was/wasn't tested).
   - Prompt-injection is mitigated by design (AI has no money path) not "solved".
   - Built with heavy AI-coding-agent assistance (I: disclose).
8. Test evidence: how to run tests, LLM cart reliability result (target >=95% valid on 20 prompts, report actual), audit-chain verify command.
9. Repo map, env vars (names only), security notes (gitleaks, no secrets), license, no trademark claim ("not affiliated with or endorsed by PayPal").

## 3. License: MIT vs Apache-2.0
- Recommend **Apache-2.0**.
  - Express patent grant + contribution terms; a payments/agent project is likelier to be reused by companies (I).
  - Includes NOTICE support; still OSI-approved, GitHub auto-detects.
  - Cost: slightly longer; irrelevant for judges.
- MIT is acceptable fallback if rules or a dependency demand it; either satisfies "OSS license" (re-verify rules for a named list).
- Check dependency licenses (AG Grid Community is MIT, V from general knowledge; I - confirm). Add NOTICE if copying anything.

## 4. The 3-minute video
Rules: under 3:00 hard (target 2:40-2:50, I: judges may stop at 3:00). No PayPal logos/trademarks in our edits (the sandbox page appears on screen unavoidably: crop/blur the logo or keep it <3 s, I; say "the payment provider's approval page" is NOT needed, we may name PayPal in speech/text as the API we use). No music (silence or own voice only; no stock tracks). No real personal data.

### Storyboard (target 2:45)
| Time | Screen | Voiceover beat |
|---|---|---|
| 0:00-0:15 | Hook: failed-delivery order, "SIMULATED CARRIER" label | "Agents can buy. Nobody agreed in advance what happens when it doesn't arrive." |
| 0:15-0:40 | Buyer signs Mandate (allowlist, cap, protection terms) | "The buyer signs the rules first: merchants, max total, and the refund promise." |
| 0:40-1:05 | Intent typed; agent cart; hard-block demo (over cap rejected by deterministic check) | "The agent only proposes. Server re-prices; AI can tighten, never loosen." (~25% runtime incl. this) |
| 1:05-1:30 | Real sandbox approve click, capture, receipt "Protected until day X (demo)" | "Real sandbox payment; receipt shows reasons." |
| 1:30-1:55 | Merchant tracking, demo-clock fast-forward, LATE detected | "Carrier is simulated; we say so." |
| 1:55-2:25 | Triage (enum + confidence), policy checks, 9 checks, refund via PayPal, sandbox shows refund | "AI classifies; deterministic policy decides; refund executes with idempotency." |
| 2:25-2:45 | Audit chain "verify" + failure case goes to HUMAN_REVIEW | "Every step is hash-chained; uncertainty fails closed." |
| 2:45-2:55 | Title card: URL + repo + "sandbox only" | One-line close. |

### Voiceover skeleton
- Hook (1 sentence problem) -> Idea (1) -> Mandate (2) -> Agent bounded (2) -> Payment (1) -> Late/lost (2) -> AI vs deterministic split (2) -> Refund + audit (2) -> Limits honesty (1: "sandbox, simulated carrier, demo-grade signing") -> Close.
- ~130 words/min speaking pace (I) -> max ~360 words total. Write script, time it with a stopwatch, cut to fit.

### Recording setup
- 1080p, 30 fps, browser zoom 125%, clean profile, dark/light consistent, notifications off, no bookmarks bar.
- Tools: OBS (screen) + separate USB/phone mic voice track, or record voice after (cleaner). Free editor (Kdenlive/DaVinci). Run on the HOSTED demo, not localhost, at least for final take.
- Pre-seed state: fresh mandate-less buyer; reset script run before every take; demo-clock control visible.
- Record in segments (per storyboard row), stitch; keep raw takes.
- Captions: hard-coded burned-in subtitles + upload an .srt (YouTube); big on-screen labels "SANDBOX", "SIMULATED CARRIER", "SEEDED CATALOG".
- Upload as unlisted early (day ~Nov 3) to test playback and embedding; set public/unlisted per rules.

### Backup video plan
- Backup A (Nov 8): complete second full recording of the same flow; keep both on YouTube (unlisted).
- Backup B: if hosted demo is down at recording, use local docker compose build against sandbox (still real sandbox calls).
- Backup C: 60-s "highlight cut" (if rules/timing prove stricter than expected).
- Never rely on a recorded flow that fakes outcomes; the video must show live sandbox calls.

## 5. Hosted-demo reliability plan
- Constraint (V, Render docs https://render.com/docs/free): free web services spin down after 15 min idle, ~1 min wake; 750 free hrs/workspace/month; filesystem ephemeral; free Postgres expires 30 days after creation (+ short grace). Hosting provider not yet chosen; apply to any free host and re-verify.
- DB expiry risk: if DB is created ~Nov 1, it expires ~Dec 1, before Dec 21 winners. Mitigation: use a free Postgres without expiry (e.g. Neon/Supabase free tier; I - verify limits) OR recreate and reseed the DB ~Dec 10; put a dated TODO.
- Keep-warm: external uptime pinger (UptimeRobot/cron-job.org free, I) hits `/healthz` every 5-10 min on gateway + each service (a request to the gateway must fan out health so downstream services wake). Check free-hours math with N services: 750 h shared across services; always-on N services > 750 h/mo if N>1 (31*24=744 h per service) => pinning all services awake can exhaust the budget (I). Decide: fewer deployable units (modular monolith in 1-2 processes) vs. wake-on-demand with a "warming up" page. Raise with architecture owner.
- Demo reset: `POST /admin/demo/reset` (token-protected) recreates seeded buyer/mandate-less state; one-click "Reset demo" in an admin page; cron nightly reset. Audit chain note: reset starts a new chain epoch, documented (append-only guarantee applies within an epoch).
- Seeded data: ~12 items, 3 virtual merchants, 1 pre-made late order in state MONITORING so judges can see a refund within 30 s without waiting; also an empty path for a full run.
- Sandbox token: ~9 h expiry (V); refresh on 401 and cache; test after 24 h idle.
- Rate/abuse: per-IP limits, LLM spend cap (hard monthly budget on the model key), CAPTCHA not needed (I). Judges may click many times: idempotent actions.
- Recorded fallback: banner "If live demo is unavailable, see the video" + video link + screenshots of a real run in README. A fallback never replaces the live demo claim.
- Status checks: scripted smoke test (create mandate -> cart -> order create) run every 6 h via cron, alerting by email to us until 12-21.
- Freeze: code freeze 11-09; only config hot-fixes after submit (rules on post-deadline changes: re-verify).

## 6. Judge-experience plan (PayPal developer advocate, first 5 minutes)
| Min | Judge does | We must have |
|---|---|---|
| 0:00 | Opens Devpost page, watches/skims video | Thumbnail + first 15 s hook |
| 0:30 | Clicks repo | README top: pitch, GIF, links, license badge |
| 1:00 | Looks for PayPal usage | "PayPal endpoints used" table, `paypal` code dir/`mcp` server, clean separation |
| 1:30 | Clicks hosted demo | Loads <5 s warm; no signup wall; guided "Start here" with 4 numbered steps |
| 2:30 | Approves in PayPal sandbox | Clear instruction + sandbox buyer creds; return works (NOT yet tested: V gap, test early) |
| 3:30 | Triggers late order / refund | One button "advance demo clock"; refund + PayPal refund ID shown |
| 4:30 | Probes honesty | Limitations section matches what the UI labels say; audit verify endpoint |
| 5:00 | Skims code quality | Tests, CI badge, idempotency (Request-Id) visible, no secrets |
- A PayPal advocate cares about (I): correct idempotency use, REST not hacks, sensible error handling (409/422 cases from spike), developer ergonomics of the MCP server (a `docs/mcp.md` with the tool list and a copy-paste config).
- Provide `docs/judge-guide.md` (1 page) and link it from Devpost.
- Consider offering the MCP server as the standalone reusable artifact (strong "Agentic Commerce" signal).

## 7. Sponsor-prize decision
| Option | Prize | Fit | Effort | Risk |
|---|---|---|---|---|
| AG Grid | 1st $5k, 2nd $2k, 3x$1k (5 winners, V blog) | Natural: audit log, reviewer queue, mandates/orders tables are grids | Low (community grid in React; sorting/filter/export) | Judged on "best use": need more than a default table (row grouping/enterprise features may need a paid license; I - verify) |
| Render | credits $1k/$750/$500 (V blog) | Hosting our services on Render is plausible | Low if we host there | Credits, not cash; free tier sleep/DB expiry (section 5) works against reliability; judged use is "hosting", weak differentiation (I) |
| Channel3 | $1.5k (V blog) | Product search API | Medium-high | Conflicts with the seeded catalog (needs real merchants/orders we cannot buy from); a contradiction with honesty rules (I) |
- **Recommend AG Grid.** Reasons: highest ceiling in cash and number of winners; low effort; real UX value (reviewer queue, audit log with chain-status column, filter by state); no architecture conflict. Render hosting can still be used incidentally, but we do not claim the Render prize (one sponsor prize per project, brief).
- Re-verify: whether the sponsor prize requires selecting it in the form and any documentation of the usage (e.g. a README section "How we use AG Grid"); whether Community vs Enterprise matters.

## 8. Devpost page copy outline
- **Title:** SafePayAI (working name; check trademark/name clash, I).
- **Tagline:** "Agents can only shop inside rules you signed - and if the order doesn't arrive, you're refunded without arguing."
- **Inspiration**
  - Agentic checkout is arriving but promises about late/lost orders are not agreed in advance (I).
  - Claims are manual (VC ~14 days average, I); card chargebacks cost merchants ($15 dispute fee, PayPal fees V).
  - We wanted the AI to be safe because it cannot touch money.
- **What it does**
  - Buyer signs a Mandate (allowlist, cap, intent, expiry, refund terms).
  - Bounded agent proposes carts; deterministic checks; AI can only tighten.
  - Real sandbox payment, tracking, late/lost detection (simulated carrier), AI triage, deterministic policy, PayPal refund.
  - Tamper-evident audit log with verify.
- **How we built it**
  - Python/FastAPI microservices behind an auth gateway; own MCP server over PayPal REST (Orders v2, tracking, Payments v2 refunds).
  - Idempotency with PayPal-Request-Id; unknown outcomes reconciled by lookup.
  - LLM with schema outputs, fail-closed; AG Grid for queue/audit views (if chosen).
  - Built with heavy AI-coding-agent help (disclose).
- **Challenges**
  - PayPal tracking cannot express late/lost/delivered (spike V) -> carrier status lives in our DB.
  - Real buyer approval click in sandbox; India vs US buyer currency issue (V).
  - Concurrent refunds returning 409; duplicate invoice_id 422 (V).
  - Making AI useful without giving it authority.
- **Accomplishments**
  - End-to-end real sandbox order -> refund path; N tests; chain verification; actual LLM cart validity % (fill in real number; do not pre-write).
- **What we learned**
  - Trust comes from limits, not model quality; idempotency details matter; honest labels beat polish.
- **What's next**
  - See section 10.
- **Built with:** python, fastapi, postgresql, paypal-rest-api, mcp, (llm provider), ag-grid, docker.
- **Try it:** hosted URL, repo, video, judge guide.

## 9. Social / community plan
| When | Channel | Post |
|---|---|---|
| Now - Oct 20 | PayPal developer community (forum/blog comments), Devpost discussion | Short "building X, what edge cases in Orders v2 refunds would you want an agent to respect?" (feedback, not promo; I: check forum norms) |
| Oct 25 | X | Build-in-public thread: the sandbox facts we learned (tracking cannot be PATCHed except CANCELLED; refund replay semantics). Real dev value, no hype |
| Nov 3 | LinkedIn | "Why the AI should never decide the refund" explainer + diagram |
| Nov 8-9 | Quiet | Final testing; no posts |
| Nov 10 (submit day) | X + LinkedIn | Submission post: 30-s clip, hosted link, repo; tag the hackathon handle/PayPal Developer (verify handle, I) |
| Nov 11-12 | PayPal developer community | Post link to the project (check rules allow community promotion; do not vote-farm) |
| Nov 13-Dec 20 | X/LinkedIn | One post per 2 weeks: limitation honesty, MCP server README, lessons |
| Dec 21 | Result posts | Thanks, regardless of outcome |
- Rules: no fake traction, no purchased votes, no PayPal logo misuse, no claims from section "Do NOT claim" (brief). Label sandbox in every clip.
- Check whether Devpost has a public-vote/"like" element (unknown); if so do NOT ask for votes unless rules permit.

## 10. Post-hackathon "what's next" (honest)
- Facts to say plainly:
  - Today: sandbox demo; simulated carrier; demo-grade signing; one shared merchant login.
  - Not done: real carrier integrations, real PayPal dispute/resolution integration, webhooks hardened, legal review, buyer-held-key signing, merchant onboarding, fraud/abuse modelling beyond 3 illustrative policies.
- Next steps (ordered by learning value):
  1. Replace simulated carrier with real tracking aggregator and measure late/lost accuracy.
  2. Webhooks as hints + reconciliation hardening; test refund PENDING and Disputes API.
  3. Buyer-held signatures (passkey/WebAuthn) for mandates.
  4. Pilot with 1-3 friendly merchants; measure refund cost vs dispute cost (we make no lift claim now).
  5. Publish the MCP server as a small reusable package with docs.
- Narrative: "PayPal's own agentic revenue is expected to matter around 2028 (VC management comment); the pre-agreed-remedy layer can be tested now." Do not claim PayPal endorses or will adopt.
- Decision gate: after Dec 21, keep or archive; if archived, say so in the README and take the demo down cleanly.

## 11. Timeline to submit
| Date | Milestone |
|---|---|
| Oct 10-20 | Re-read official Devpost rules; resolve all "re-verify" items; pick license; create repo with LICENSE, `.env.example`, gitleaks CI |
| By Oct 31 | Feature complete vertical slice on hosted demo; return-URL test (V gap) |
| Nov 1-5 | README, architecture diagram, judge guide; first video draft |
| Nov 6-8 | Final video + backup; smoke tests; AG Grid README section |
| Nov 9 | Code freeze |
| Nov 10 | SUBMIT; social posts |
| Nov 11-12 | Buffer only |
| Dec 21 | Winners; demo stays up until then |

## 12. Open questions
- Exact Devpost wording on video visibility, repo, license, edit-after-submit, one sponsor prize selection, AI-assisted-coding disclosure (not fetched).
- Prize total conflict ($60k vs $67.5k) - do not cite.
- Deadline timezone conflict between secondary sources - trust Devpost timer.
- Hosting free-hours vs N microservices and DB expiry (needs architecture owner).
