# triage-ai

Classifies untrusted buyer text, drafts gated messages, and builds a read-only reviewer
brief. Per ADR-010, AI never decides money: every output is validated against a strict
JSON Schema and fails closed to `HUMAN_REVIEW` / static templates on any error. Caller
allowlist is `resolution` only; this service makes no outbound HTTP calls to any other
service and holds no PayPal credentials.

## Run alone

```
uv sync
uv run uvicorn app.main:app --reload
```

Requires a Postgres reachable at `PS_TRIAGEAI_DATABASE_URL` with schema `triage` migrated:

```
uv run alembic upgrade head
```

## Test

```
uv run pytest
```

## Status

Fully implemented with real Gemini/Groq calls through `app/llm_provider.py`.
`resolution`'s `/classify` contract was wrong for most of this project's history (sent/
parsed a shape that never matched this service's real, already-correct schema) — fixed
on the `resolution` side; this service's own `/classify`, `/draft`, `/brief` were never
the problem. Known gap: `resolution` currently sends an empty `timeline` and
`item_titles` on every real call (neither `tracking` nor `checkout` expose that data
yet), so this service's `InconsistencyFlag`/timeline-consistency output is weaker than
designed until that's wired up.
