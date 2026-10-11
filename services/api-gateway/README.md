# api-gateway

Single public entry point for SafePayAI's web app. Terminates gateway-owned demo
sessions (cookie), mints short-lived internal service JWTs per upstream call,
proxies `/api/<svc>/*` to the owning service, and enforces CSRF/CORS/rate limits
and header stripping. Owns only the `gateway` schema (users, sessions, csrf_uses,
signing_keys, settings) - no business data.

Wave 5 status: real logic for sessions/login/logout, argon2id passwords, RS256
internal JWT minting + `/.well-known/jwks.json` with kid rotation, role guards,
an in-process rate limiter on auth endpoints, and the generic `/api/<svc>/*`
proxy (header allowlist, JWT mint, forward, response filter, idempotency and
money-routes checks). `GET /api/auth/csrf` and the ops/BFF endpoints remain
`501 not_implemented` stubs - out of this pass's scope; see the handoff notes in
the PR/report for the full list of flagged scope cuts and deviations.

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
