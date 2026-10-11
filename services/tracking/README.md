# tracking

Owns the carrier/delivery state machine for SafePayAI. PayPal cannot represent late/lost/
delivered status (verified sandbox limitation, see `00-context-brief.md` section 3) — this
service's own DB is the source of truth for shipment status, with a demo clock for
simulating delays. Wave 4: FastAPI skeleton, health/readyz, stubbed routes, baseline schema.

## Run alone

```
uv sync
uv run uvicorn app.main:app --reload
```

Requires a Postgres reachable at `PS_TRACKING_DB_URL` with schema `tracking` migrated:

```
uv run alembic upgrade head
```

## Test

```
uv run pytest
```

## Status

Wave 4 scaffold only: every route except `/health`, `/healthz`, `/readyz`, `/healthz/deep`
returns `501 Not Implemented`. Business logic (state machine, poller/tick, demo-clock
guards, PayPal tracker sync) lands in Wave 5.
