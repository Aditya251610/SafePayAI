# resolution

Owns the 12-state case machine and the `REFUNDS_FROZEN` global kill switch for SafePayAI.
Deterministic policy decides refund/review outcomes; AI (triage-ai) never decides money
(ADR-010). Wave 4: FastAPI skeleton, health/readyz, stubbed routes, baseline schema with
`control_flags` seeded `refunds_frozen = true` (fail closed).

## Run alone

```
uv sync
uv run uvicorn app.main:app --reload
```

Requires a Postgres reachable at `PS_RESOLUTION_DATABASE_URL` with schema `resolution`
migrated:

```
uv run alembic upgrade head
```

## Test

```
uv run pytest
```

## Status

Wave 4 scaffold only: every route except `/health`, `/healthz`, `/readyz`, `/health/deep`
returns `501 Not Implemented`. `GET/PUT /controls/refunds-frozen` checks the settings flag
but still 501s — the real DB-row kill switch, the 12-state machine, and the 9 ordered
pre-refund checks land in Wave 5.
