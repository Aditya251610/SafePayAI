# Render Profile B: environment checklist

Four hosts: `safepayai-edge` (api-gateway), `safepayai-core` (mandate, catalog, checkout,
tracking, resolution, audit), `safepayai-ai` (shopping-agent, triage-ai), `safepayai-paypal`
(paypal-adapter). Service defaults are **localhost/dev values**, so every setting below must be
present on the live hosts or a hop of the journey silently breaks.

## Non-secret settings (in git)

`render-env.json` holds them; `python3 scripts/render_apply_env.py` (dry run) shows drift and
`--apply` fixes it and redeploys. The file only lists values that were found missing on the
live deploy, each with the symptom it caused:

| Setting group | Symptom when missing |
|---|---|
| `PS_SHOPPINGAGENT_LLM_*`, `PS_TRIAGEAI_LLM_*` (model names, timeouts) | model names default to `None`: the AI fails closed on every call and only the deterministic matcher answers (`model: null`) |
| `PS_CHECKOUT_HTTP_TIMEOUT_*`, `PS_APIGATEWAY_UPSTREAM_*_TIMEOUT_S`, `PS_PAYPALADAPTER_PAYPAL_TIMEOUT_SECONDS`, `PS_RESOLUTION_*_TIMEOUT_S` | 2 s defaults are shorter than a Neon/cold-host round trip: `MANDATE_UNAVAILABLE`, 504 on confirm |
| `PS_CHECKOUT_RETURN_BASE_URL`, `PS_PAYPALADAPTER_PAYPAL_RETURN_URL_ALLOWED_ORIGINS` | PayPal redirects the buyer to `http://localhost:3000` after approval |
| `PS_TRACKING_SANDBOX_MODE`, `PS_TRACKING_DEMO_CONTROLS_ENABLED`, `PS_RESOLUTION_DEMO_MODE`, `PS_APIGATEWAY_DEMO_MODE` | demo clock/force routes 404; LATE/LOST outcome profiles are ignored |
| `PS_TRACKING_SERVICE_SIGNING_KID`, `PS_RESOLUTION_INTERNAL_JWT_KID` (= `k1`, the gateway key) | tracking/resolution mint no service token, so cross-service calls 401 |
| `PS_RESOLUTION_INTERNAL_JWT_TRUSTED_ISSUERS` | resolution rejects tracking's late/lost events (401); no case ever opens |

## Secrets (never in git; set in the Render dashboard or via the API from `.env`)

Names only. Copy values from your local `.env`; do not print them.

- every service: `PS_<SLUG>_DATABASE_URL`
- gateway: `PS_APIGATEWAY_SIGNING_KEY_PEM`, `PS_APIGATEWAY_TICK_SECRET`,
  `PS_APIGATEWAY_TRACKING_TICK_SECRET`, `PS_APIGATEWAY_RESOLUTION_TICK_SECRET`
- core: `INTERNAL_TICK_SECRET`, `PS_RESOLUTION_TICK_SECRET`, `PS_TRACKING_SERVICE_SIGNING_KEY`,
  `PS_RESOLUTION_INTERNAL_JWT_SIGNING_KEY`, the HMAC keys, `PS_AUDIT_TRUSTED_ISSUERS`
- ai: `PS_SHOPPINGAGENT_GEMINI_API_KEY`, `PS_SHOPPINGAGENT_GROQ_API_KEY` (and triage-ai's)
- paypal: `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PS_PAYPALADAPTER_OUTBOX_FLUSH_SECRET`

## Known open item: audit relay keys

Producers push outbox events to audit with a **development** relay key built into
`libs/common` (kid `ps-outbox-relay-dev`), which audit's production trusted-issuer map rightly
does not include, so `POST /audit/internal/events/batch` returns 401 and only the genesis
entry is in the chain. Do not "fix" it by trusting the dev key (its private half is in the
repo). Generate a fresh keypair, give each producer `PS_<SLUG>_OUTBOX_RELAY_JWT_PRIVATE_KEY` +
`PS_<SLUG>_OUTBOX_RELAY_JWT_KID`, and add only the public key to `PS_AUDIT_TRUSTED_ISSUERS`.

## Free-tier behavior

Hosts sleep after ~15 minutes idle and take 30-45 s to wake; the first request can return a
non-JSON wake-up page. `keepwarm.yml` pings them on a schedule; warm them before a demo.
