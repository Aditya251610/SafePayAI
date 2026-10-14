# checkout

Owns cart pricing/checks, PayPal order creation and capture orchestration, receipts, and the
order state machine for SafePayAI. Calls catalog, mandate, shopping-agent (advisory
intent-fit) and paypal-adapter; never calls PayPal directly and never holds a PayPal
credential.

Fully implemented and live-tested against the real PayPal sandbox: cart pricing/checks
(`/carts`, `/carts/{id}/confirm`), the full order flow (PayPal order creation, real
browser-approved capture, return/cancel handling, receipts), all real — verified across
multiple fresh sandbox checkouts (not mocked). `POST /internal/events`,
`GET /internal/outbox`, and `POST /internal/reconcile` remain `501 not_implemented`
(internal catch-up/reconcile tooling, not on the hot money path). See
`.claude/prd/services/checkout/{spec,api,deployment}.md` for the full contract.

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
