# shopping-agent

Bounded cart-proposal and intent-fit service for SafePayAI. Turns a buyer's free-text intent
(or form fields) into a validated cart of catalog SKUs, and gives checkout an advisory
intent-fit verdict. Never sets a price, total, or merchant; never touches money or PayPal.
One of only two services (with triage-ai) allowed LLM provider keys (ADR-010); raw model
output never reaches a money-moving path.

Wave 4 status: contracts + skeleton only. `/healthz` and `/readyz` work; every other route
(`/propose`, `/intent-fit`, `/internal/outbox/*`) returns `501 not_implemented`. The LLM
provider adapters (`app/llm_providers.py`) are wired to `safepayai_common`'s gateway
interface but raise `NotImplementedError` -- no real Gemini/Groq calls yet.

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
