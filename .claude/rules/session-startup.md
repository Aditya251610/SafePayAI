---
paths:
  - "**/*"
---

# Session startup & task-lookup rule (HARD RULE)

- Session start: if `.claude/handoff/` contains a handoff doc (filename `handoff-YYYY-MM-DD-HHmm.md`) newer than ~48 hours old, load the newest one alongside CLAUDE.md and any active agent files as an initial step.
- Before starting any task the user asks for: first check the newest handoff doc — has this (or part of it) already been done in a prior session? Then check `.claude/memory/index.md` for entries whose tags match the task. Read whichever of these is relevant before touching code files.
- Keep the working context small: prefer the most relevant memory entries and skip broad reads unless the user explicitly asks for full-project review.
- Never read files or folders listed in `.claudeignore` (if that file exists at the repo root), under any circumstance — not via Read, Grep, Glob, Bash `cat`/`find`, or any other tool.
