# SafePayAI

A buyer-signed spending **Mandate** + a bounded shopping agent + a deterministic late/lost-order
protection loop, built on the PayPal sandbox for the PayPal AI Hackathon 2026.

The agent proposes carts under a signed mandate (merchant allowlist, spend cap, expiry,
pre-authorized refund terms) but never holds PayPal credentials and never executes payment itself.
A deterministic policy engine — not the AI — decides refunds; AI only classifies and drafts,
fails closed to human review on any uncertainty. Every money-moving action is logged in a
hash-chained audit trail.

## Status

**Backend complete and live-tested end to end against the real PayPal sandbox.** All 10 backend
services (`api-gateway`, `mandate`, `catalog`, `shopping-agent`, `checkout`, `paypal-adapter`,
`tracking`, `resolution`, `triage-ai`, `audit`) have real business logic, not stubs. Verified live,
twice, with real PayPal sandbox orders (not mocked): the automated late/lost detection → case →
offer → buyer accept → refund loop, the buyer-report → AI triage → human-reviewer → approval-link
→ refund loop, merchant-override and reship paths, mandate revocation correctly blocking future
(not past) protection, and real PayPal webhook delivery + signature verification (a real sandbox
webhook subscription, delivered to a temporary public tunnel, passed verification end to end).
Frontend (`services/web`) has not been started — backend-first build order, per project convention.

Full `authorization_ticket` HMAC verification is now wired and live-verified at the paypal-adapter
boundary (checkout and resolution mint real tickets, paypal-adapter verifies the HMAC signature and
binds it to the exact mandate/amount/currency on both REST and MCP paths — not just a presence
check), and duplicate-refund, timeout-after-success, replay/reconcile-against-genuinely-UNKNOWN, and
concurrent refund attempts are covered by integration tests against a real Postgres.

Known remaining gaps: AI triage's injection/timeline-consistency signal is weaker than designed
(tracking doesn't yet expose a per-shipment-event timeline to triage-ai).

## Honesty / limitations (read this before judging)

- **Sandbox only.** All PayPal calls hit the PayPal **sandbox** environment, never production money.
- **Simulated carrier.** There is no real shipping carrier integration — delivery/tracking status
  is a **SIMULATED CARRIER** clock we control, clearly labelled on screen wherever shown.
- **Seeded catalog.** Products are a small seeded demo catalog, not a live marketplace.
- We do not claim "PayPal-backed", "PayPal-verified", legal non-repudiation, regulatory compliance,
  or that any part of this is fraud-proof or injection-proof. Refunds are described accurately as
  "merchant-funded, issued via the PayPal Payments v2 refund API."

## Run locally

```bash
cp .env.example .env   # fill in sandbox PayPal credentials; never commit this file
docker compose up
```

Each service also runs standalone: `cd services/<slug> && uv run uvicorn app.main:app --reload`.

## Architecture

11 services in one monorepo: `api-gateway`, `mandate`, `catalog`, `shopping-agent`, `checkout`,
`paypal-adapter`, `tracking`, `resolution`, `triage-ai`, `audit`, `web`. Each service owns its own
Postgres schema and DB role; services never share database access directly. OpenAPI contracts for
every backend service live in [`contracts/openapi/`](contracts/openapi/). Shared, business-logic-free
infra (JWT verify/mint, the money-ticket HMAC helper, DB grants, HTTP client defaults, the LLM
gateway interface) lives in [`libs/common`](libs/common).

- `services/api-gateway` — auth/session edge, issues internal service JWTs
- `services/mandate` — buyer-signed spending mandate (cap, merchant allowlist, expiry, refund terms)
- `services/catalog` — seeded demo product catalog (read-only at runtime)
- `services/shopping-agent` — proposes carts under a mandate; no PayPal credentials, no payment execution
- `services/checkout` — cart → PayPal order → capture orchestration
- `services/paypal-adapter` — the only service holding PayPal sandbox credentials; REST + a small MCP surface
- `services/tracking` — simulated carrier/delivery state machine (PayPal tracking can't represent this; see adapter notes)
- `services/resolution` — deterministic refund/resolution policy engine and case state machine
- `services/triage-ai` — AI classification/drafting only; never decides money, fails closed to human review
- `services/audit` — append-only, hash-chained audit log
- `services/web` — Next.js frontend (built after the backend, per the current build order)

Building the frontend (or any other client of the gateway)? Start with
[`contracts/frontend-integration-contract.md`](contracts/frontend-integration-contract.md) —
every `/api/*` route, role, CSRF, and idempotency requirement, read directly from the
gateway's own code. No need to read any backend service's source to integrate against it.

## License

MIT — see [`LICENSE`](LICENSE).
