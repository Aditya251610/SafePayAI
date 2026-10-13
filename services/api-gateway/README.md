# api-gateway

Single public entry point for SafePayAI's web app. Terminates gateway-owned demo
sessions (cookie), mints short-lived internal service JWTs per upstream call,
proxies `/api/<svc>/*` to the owning service, and enforces CSRF/CORS/rate limits
and header stripping. Owns only the `gateway` schema (users, sessions, csrf_uses,
signing_keys, settings) - no business data.

Real logic for sessions/login/logout, argon2id passwords, RS256 internal JWT
minting + `/.well-known/jwks.json` with kid rotation (this is the JWKS every
other backend service verifies internal tokens against), role guards, an
in-process rate limiter on auth endpoints, `GET /api/auth/csrf`, and the
generic `/api/<svc>/*` proxy (header allowlist, JWT mint, forward, response
filter, idempotency and money-routes checks). The ops endpoints
(`/api/ops/status|freeze|tick`) and the BFF read endpoints
(`/api/bff/buyer-home|orders/{id}|merchant-queue`) remain `501 not_implemented`
— these are frontend-facing convenience aggregation endpoints, not on the
backend money path, and were out of scope while the backend was built directly
against each service.

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
