# catalog

Seeded, read-only product catalog for SafePayAI (12 items, 3 virtual merchants,
sandbox/demo data only). Serves item/merchant/category listings and server-authoritative
price resolution; never trusts a caller-supplied price.

Fully implemented: item/merchant/category listings, server-authoritative price
resolution, and the seeded demo catalog (12 items, 3 merchants) all real and in use
by every live checkout flow run against this backend.

## Run alone

```
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

## Test

```
uv run pytest
```

See `.claude/prd/services/catalog/{spec,api,deployment}.md` for full contracts and
`contracts/openapi/catalog.yaml` for the machine-readable OpenAPI contract.
