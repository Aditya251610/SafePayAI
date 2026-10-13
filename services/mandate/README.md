# mandate

Pure authority service for SafePayAI: signs and holds the immutable buyer Mandate
(terms + hash + HMAC), enforces the spend ledger (reservations, spent/reserved
counters) under row locks, and issues per-order protection grants that survive
revoke/expiry. No LLM, no PayPal credentials, no catalog dependency.

Fully implemented and live-tested against the real PayPal sandbox: sign, canonicalize/
hash/HMAC, evaluate/reserve/commit/release spend reservations under row locks, and
revoke (verified live — a real revoked mandate correctly blocks protection for any
case opened against it afterward, while cases already opened under it keep their
frozen terms snapshot, per the confirmed "revoke = future spend only" rule).

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
