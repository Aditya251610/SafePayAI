# Agent Memory Index

Automatically maintained by Claude agents. Tracks learnings, decisions, and corrections discovered during the project.

**Rules for agents:**
- Read this index at session start. Load specific entries only if tags match the current task.
- After every response: if a new learning, correction, or decision occurred, create/update an entry and add it to this table.
- Corrections replace old entries — delete the stale row and file, add the new one.
- Entries should stay short and specific. Tags must be precise enough to match future tasks.

## Entries

| Date | ID | Tags | Summary |
|------|----|------|---------|
| 2026-10-11 | [hackathon-product-selection](entries/hackathon-product-selection.md) | hackathon, paypal, ai, product, selection, safepayai, prd | Product is "SafePayAI" (renamed from "Made Whole"/ARTIQ pivot). Full PRD built across 3 waves in `.claude/prd/` (source of truth — see its README.md) covering all 11 services, architecture, sprint plan, and 10 confirmed platform decisions. Wave 4 (scaffolding: repo init, OpenAPI contracts, docker-compose, migrations) not yet started — zero code/config exists. Devpost hackathon rules unconfirmed (403-blocked). See `.claude/handoff/handoff-2026-10-11-0839.md` for full session handoff. |
