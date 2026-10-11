# checkout

Owns cart pricing/checks, PayPal order creation and capture orchestration, receipts, and the
order state machine for SafePayAI. Calls catalog, mandate, shopping-agent (advisory
intent-fit) and paypal-adapter; never calls PayPal directly and never holds a PayPal
credential.

Wave 4 status: contracts + skeleton only. `/healthz` and `/readyz` work; every other route
(`/carts`, `/carts/{id}/confirm`, `/orders/*`, `/internal/*`) returns `501 not_implemented`.
No business logic, no real PayPal calls yet -- see
`.claude/prd/services/checkout/{spec,api,deployment}.md` for the Wave 5 contract.

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
