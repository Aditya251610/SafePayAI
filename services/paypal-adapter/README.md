# paypal-adapter

The only service holding PayPal credentials. Thin anti-corruption layer over PayPal
sandbox REST (Orders v2, tracking, refunds), exposed over REST (`/v1/*`) and a hand-written
MCP JSON-RPC stub (`/mcp`) sharing one `ops` implementation so REST and MCP cannot diverge.
Money tools (`create_order`, `capture_order`, `refund_capture`) require a caller-allowlist
match plus a signed `authorization_ticket` (verified with
`safepayai_common.auth.ticket.verify_ticket`); never routed by `api-gateway`.

Wave 4 status: contracts + skeleton only. `/healthz`, `/health`, and `/readyz` work
(including a sandbox-host guard check in `/readyz`). Every REST tool route and the MCP
`tools/call` method return a `501`/`isError` stub. No real PayPal API calls exist in this
codebase yet -- see `.claude/prd/services/paypal-adapter/{spec,api,deployment}.md`.

## Run standalone

```
uv sync
cp .env.example .env   # edit DB URL and sandbox credentials at minimum
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
