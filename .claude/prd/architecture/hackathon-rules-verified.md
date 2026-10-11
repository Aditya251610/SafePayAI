# PayPal AI Hackathon — Rules Verification

**Checked:** 2026-10-10
**Official Devpost page (paypalaihackathon.devpost.com) returned HTTP 403 to WebFetch on all attempted paths (/, /rules, /details). web.archive.org also unreachable from this tool.**
**No fact below could be confirmed on the primary source itself. Everything is labelled VC (secondary/unverified) with source cited. Re-check directly in a browser before finalizing.**

## 1. Submission deadline
- VC (coursejoiner.com, 3rd-party aggregator): **November 13, 2026, 1:30 AM GMT+5:30** — this converts to **Nov 12, 2026, ~8:00 PM UTC / 12:00 PM (noon) PT / 3:00 PM ET**. So "noon PT" and "3pm EST/ET" are likely the SAME moment expressed in different zones, not conflicting data — both are plausibly correct for the same deadline.
- VC (developer.paypal.com/community/blog/PayPal_AI_Hackathon, official PayPal blog, but not the Devpost rules page): deadline stated only as **"Nov 12, 2026 — submissions close"** end of a 6-week build window, no time/timezone given.
- **Action:** confirm exact time/timezone on Devpost itself; current best estimate is noon PT / 3pm ET on Nov 12, 2026 (consistent with both prior figures).

## 2. Total prize amount
- VC (PayPal official blog): **"$60,000+ USD in cash"** (headline figure, 1st place Best Overall = $12,000).
- VC (coursejoiner.com): **"$67,500+ in cash prizes"**, likely the sum of main + category + sponsor cash prizes (sponsor credits/subscriptions excluded from that figure).
- The $69,750 figure from prior planning docs was **not found in any source** today — could not confirm or find its origin. Treat as unconfirmed/likely stale.
- Best current estimate: **$67,500+ cash** is more precise/likely correct than the simpler "$60k+" headline; $69,750 is unverified and possibly wrong.

## 3. Judging criteria / weights
- **Not found/stated in any source**, official or secondary. No page lists judging criteria text or weight percentages.
- The "equal weights" assumption in prior docs is **unverified — not confirmed, not contradicted**. No published weighting exists in any source found. Flag as still-open/unknown rather than "assumed equal."

## 4. Submission requirements
- VC (coursejoiner.com): integrate ≥1 PayPal API/SDK/technology (Sandbox) meaningfully; incorporate AI/ML/agents into core UX or backend; working functional prototype (no static mockups); submit via Devpost.
- **No source (official or secondary) mentions**: public repo requirement, OSS license requirement, hosted demo vs. run-instructions, YouTube demo video <3 min, written description, or team-size rules. None of these could be confirmed or denied — they may be standard Devpost boilerplate requirements not visible without accessing the actual rules page. **Do not treat prior doc's claims about repo/license/video as confirmed** — currently unverified both ways.

## 5. "One sponsor prize per project" rule
- **No source mentions this rule at all**, in either direction. Could not confirm it exists or find exact wording. Treat as prior inference, status still unconfirmed — not found as published text anywhere accessible today.

## 6. Eligibility restrictions
- VC (coursejoiner.com): must be above legal age of majority in country of residence; open globally "excluding standard restricted regions subject to legal exceptions" (no specific country list given); solo or team entries allowed; both new and meaningfully-updated existing projects qualify; free registration.
- No specific excluded-country list found in any source. Prior docs' "excluded countries" note could not be confirmed or refuted — no list located.

## 7. AI-tool / coding-agent disclosure requirements
- VC (coursejoiner.com): states participants "may use any AI tool or model of their choice" — permissive, no disclosure requirement mentioned.
- No source requires disclosing use of Claude Code or any other coding agent specifically. Unconfirmed either way beyond this general permissive statement.

## Sources consulted
- https://paypalaihackathon.devpost.com/ , /rules, /details — all 403 Forbidden, could not read
- https://web.archive.org/... — tool blocked from fetching
- https://developer.paypal.com/community/blog/PayPal_AI_Hackathon (official PayPal blog, partial info)
- https://coursejoiner.com/hackathon/paypal-ai-hackathon-2026/ (third-party aggregator, most detailed but unverified/unofficial)
- Various WebSearch queries returned no additional direct Devpost content or cached snippets of the rules page.

## Overall confidence
LOW-MEDIUM. No official primary-source confirmation achieved today. Strongly recommend someone manually open https://paypalaihackathon.devpost.com/rules in a logged-in browser (the 403 may be bot-blocking, not a dead page) before locking any PRD assumptions, especially judging weights, exact submission format, and the sponsor-prize-limit rule — none of which could be found anywhere, official or secondary.
