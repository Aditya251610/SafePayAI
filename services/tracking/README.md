# tracking

Owns the carrier/delivery state machine for SafePayAI. PayPal cannot represent late/lost/
delivered status (verified sandbox limitation, see `00-context-brief.md` section 3) — this
service's own DB is the source of truth for shipment status, with a demo clock for
simulating delays.

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

Fully implemented and live-verified: the demo-clock-driven state machine, the late/lost
detector, and the auto-case-open push to `resolution` all work end to end (verified live
multiple times, including a fresh real PayPal sandbox order). The real PayPal tracker
mirror call (`add_tracking`/`cancel_tracking` against `paypal-adapter`) is implemented
with the correct real field names, but has been observed to get rejected (422) by PayPal
itself when attempted against an already-fully-refunded sandbox order — a sandbox
state/data limitation hit during testing, not re-confirmed against a genuinely fresh,
still-open order. Late/lost/delivered status itself always comes from this service's own
DB (SIMULATED CARRIER), never from the PayPal mirror call either way.
