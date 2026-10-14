# paypal-adapter

The only service holding PayPal credentials. Thin anti-corruption layer over PayPal
sandbox REST (Orders v2, tracking, refunds), exposed over REST (`/v1/*`) and a hand-written
MCP JSON-RPC stub (`/mcp`) sharing one `ops` implementation so REST and MCP cannot diverge.
Money tools (`create_order`, `capture_order`, `refund_capture`) require a caller-allowlist
match plus a signed `authorization_ticket` (verified with
`safepayai_common.auth.ticket.verify_ticket`); never routed by `api-gateway`.

Fully implemented and live-verified against the real PayPal sandbox: `create_order`,
`get_order`, `capture_order`, `refund_capture`, `get_refund`, `get_capture`, tracker
add/get/cancel, and the DB-backed `control` kill switch (OR'd with the static env var)
all make real PayPal API calls, confirmed live across multiple fresh sandbox checkouts
and real refunds. Webhook signature verification is implemented but NOT re-confirmed
against a real PayPal-sent webhook — there's no way to receive one in local dev; it
returns a clear `{"ok": false, "status": "DISABLED"}` when disabled (the default) rather
than pretending to process webhooks. Full `authorization_ticket` HMAC verification is
still deferred (the router dependency only checks the header is present, not its
signature) pending checkout/resolution as ticket minters.

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
