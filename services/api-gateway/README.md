# api-gateway

Single public entry point for SafePayAI's web app. Terminates gateway-owned demo
sessions (cookie), mints short-lived internal service JWTs per upstream call,
proxies `/api/<svc>/*` to the owning service, and enforces CSRF/CORS/rate limits
and header stripping. Owns only the `gateway` schema (users, sessions, csrf_uses,
signing_keys, settings) - no business data.

Wave 4 status: contracts + skeleton only. All routes except `/healthz`, `/readyz`
return `501 not_implemented`, including `/.well-known/jwks.json` and the
session/login endpoints (modeled per spec.md but not wired up). Session mechanics,
JWT minting, CSRF, rate limiting, and the real proxy pipeline land in Wave 5.

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

See `.claude/prd/services/api-gateway/{spec,api,deployment}.md` for full contracts
and `contracts/openapi/api-gateway.yaml` for the machine-readable OpenAPI contract.
