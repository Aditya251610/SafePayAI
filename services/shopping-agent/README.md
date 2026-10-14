# shopping-agent

Bounded cart-proposal and intent-fit service for SafePayAI. Turns a buyer's free-text intent
(or form fields) into a validated cart of catalog SKUs, and gives checkout an advisory
intent-fit verdict. Never sets a price, total, or merchant; never touches money or PayPal.
One of only two services (with triage-ai) allowed LLM provider keys (ADR-010); raw model
output never reaches a money-moving path.

`/propose` and `/intent-fit` are fully implemented with real Gemini/Groq calls through
`app/llm_providers.py` (verified via a labelled eval harness, `evals/`, including
injection-attempt cases and a printed fail-closed rate — real provider keys live in
`.env`, use sparingly, free-tier RPM/RPD caps can exhaust). `GET /internal/outbox`
remains `501 not_implemented` (a debug/catch-up endpoint, not on the money path).

## Run standalone

```
uv sync
cp .env.example .env   # edit DB URL at minimum
uv run uvicorn app.main:app --reload
```

## Test

```
uv run pytest
```

## Migrate

```
uv run alembic upgrade head
```

See `.claude/prd/services/shopping-agent/{spec,api,deployment}.md` for the full contract.
