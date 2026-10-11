Triggered by `/scaffold` or "scaffold"/"stub this out" language in a request.

## When to use

Only for explicit scaffold requests. A plain feature or bug-fix request always gets real, working code — never a skeleton. If a request is ambiguous ("scaffold" could mean either), ask which is meant before proceeding.

## What to produce

Use the current repo patterns and project conventions as the canonical shape:
- File-level doc comment explaining what the file is responsible for.
- Import placeholders — list what will actually be needed, not filled in.
- Function body made entirely of plain-English, step-by-step comments describing what will happen.
- No real implementation code at all.

## Adapting the shape

Adapt per file type while keeping the comments-only rule:
- Component or UI screen — props/comment for what it renders, no logic.
- Route or page — describe responsibility and required data.
- API client or service — describe which endpoint or resource it talks to and what it returns.
- Hook or state manager — comment inputs/outputs and when it re-fetches or updates.

## Stopping condition

Stop scaffolding and switch to real implementation the moment the user asks to "fill in", "implement", or "make this work."
