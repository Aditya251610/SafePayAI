Write a handoff document summarising the current conversation so a fresh agent can continue the work. Save to `.claude/handoff/` in the current workspace (create the directory if it doesn't exist).

Filename: `handoff-YYYY-MM-DD-HHmm.md` (local time at write time) — the timestamp is how a future session judges whether it's recent enough to auto-load (see `.claude/rules/session-startup.md`). If multiple exist, the newest filename is the one that matters; older ones can stay for history.

Include:
- Task goal and current status
- Files changed and why
- Decisions made (and why)
- Failing tests or known blockers
- Exact next steps
- Suggested skills to invoke in the next session

Do not duplicate content already captured in other artifacts (PRD, plans, issues, commits, diffs). Reference them by path instead.

Redact any sensitive information: API keys, passwords, personally identifiable information.

If the user passed arguments, treat them as a description of what the next session will focus on and tailor the doc accordingly.
