# mandate

Pure authority service for SafePayAI: signs and holds the immutable buyer Mandate
(terms + hash + HMAC), enforces the spend ledger (reservations, spent/reserved
counters) under row locks, and issues per-order protection grants that survive
revoke/expiry. No LLM, no PayPal credentials, no catalog dependency.

Wave 4 status: contracts + skeleton only. All routes except `/healthz`, `/readyz`
return `501 not_implemented`. Canonicalization, hashing/HMAC, state derivation,
evaluate/reserve/commit business logic lands in Wave 5.

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

See `.claude/prd/services/mandate/{spec,api,deployment}.md` for full contracts and
`contracts/openapi/mandate.yaml` for the machine-readable OpenAPI contract.
