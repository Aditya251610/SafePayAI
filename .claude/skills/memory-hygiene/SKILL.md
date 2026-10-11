Run when the user invokes `/memory-hygiene`, or asks to clean up/prune memory, or notices `.claude/memory/entries/` or `index.md` growing large.
This is a separate concern from the memory skill that handles per-response writes — this one handles periodic pruning.

## Steps

1. Read `.claude/memory/index.md` in full, then read every entry file it points to (or only the ones matching the user's scoping argument, if given).
2. Classify each entry:
   - KEEP — still-relevant fact, correction, or decision; nothing supersedes it; would help a future session.
   - STALE/RESOLVED — describes a bug/gap that is now fixed and has no lasting explanatory value.
   - SUPERSEDED — a later entry fully covers or corrects it. Delete the older one.
   - DUPLICATE/OVERLAPPING — merge into a single entry.
   - AGED OUT — older than ~90 days, no tag overlap with recent work, purely historical with no standing rule.
3. For every DELETE/MERGE: remove the entry file(s), remove the matching index row(s). For merges, write the consolidated entry and a single index row.
4. Never delete:
   - Anything describing a standing user preference or correction.
   - Anything CLAUDE.md, `.claude/rules/`, or another still-kept entry actively links to.
5. Report a short summary at the end: count removed / merged / kept-but-flagged-as-borderline, and one line per removal explaining why.

## Guardrails

- Age alone is never sufficient reason to delete.
- When genuinely unsure whether something is stale, keep it and name it expressly as borderline.
- If in doubt about an ongoing-effort entry, check current repo state before deciding.
