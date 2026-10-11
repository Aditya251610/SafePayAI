# catalog

Seeded, read-only product catalog for SafePayAI (12 items, 3 virtual merchants,
sandbox/demo data only). Serves item/merchant/category listings and server-authoritative
price resolution; never trusts a caller-supplied price.

Wave 4 status: contracts + skeleton only. All routes except `/health`, `/healthz`,
`/readyz` return `501 not_implemented`. Business logic (pricing algorithm, seeding
admin flows) lands in Wave 5.

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
