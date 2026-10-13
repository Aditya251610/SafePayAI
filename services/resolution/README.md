# resolution

Owns the 12-state case machine and the `REFUNDS_FROZEN` global kill switch for SafePayAI.
Deterministic policy decides refund/review outcomes; AI (triage-ai) never decides money
(ADR-010). `control_flags` is seeded `refunds_frozen = true` (fail closed).

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

Fully implemented and live-tested against the real PayPal sandbox (twice, including a
fresh-data end-to-end pass). The 12-state case machine, the 9 ordered pre-refund checks,
the DB-row `REFUNDS_FROZEN` kill switch (OR'd with paypal-adapter's own), the automated
DETECTOR-origin loop (late/lost → case → offer → refund), the buyer-report loop (triage
classification → reviewer decision → approval link → refund), merchant-override and reship
paths, and mandate-revocation-blocks-future-protection are all real and verified live.

Known gaps: AI triage's `timeline`/`item_titles` inputs are always empty (tracking has no
per-event history endpoint, checkout exposes no line items yet), so triage's
inconsistency-flagging signal is weaker than designed. Concurrency races beyond basic CAS
testing and `/refunds/reconcile` replay against a genuinely UNKNOWN attempt are untested.
