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

Wave 4 scaffold only: `/classify`, `/draft`, `/brief` return `501 Not Implemented` after
auth/schema validation. `/health`, `/healthz`, `/readyz`, `/health/deep` are real. The LLM
provider adapters in `app/llm_provider.py` are wired to `libs/common`'s `LLMGateway`
interface but raise `NotImplementedError` on every call — no Gemini/Groq SDK calls exist
yet; that is Wave 5.
