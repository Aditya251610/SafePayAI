# SafePayAI

A buyer-signed spending **Mandate** + a bounded shopping agent + a deterministic late/lost-order
protection loop, built on the PayPal sandbox for the PayPal AI Hackathon 2026.

The agent proposes carts under a signed mandate (merchant allowlist, spend cap, expiry,
pre-authorized refund terms) but never holds PayPal credentials and never executes payment itself.
A deterministic policy engine — not the AI — decides refunds; AI only classifies and drafts,
fails closed to human review on any uncertainty. Every money-moving action is logged in a
hash-chained audit trail.

**Full product/technical documentation (source of truth): [`.claude/prd/README.md`](.claude/prd/README.md).**

## Status

Wave 4 (repo scaffolding: service skeletons, OpenAPI contracts, CI) — in progress. No business
logic is implemented yet; that is Wave 5 per [`.claude/prd/sprint-plan.md`](.claude/prd/sprint-plan.md).

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

See [`.claude/prd/architecture/deployment-zero-cost.md`](.claude/prd/architecture/deployment-zero-cost.md)
for the hosted-demo deployment profile and [`.claude/prd/architecture/ci-cd-and-repo-workflow.md`](.claude/prd/architecture/ci-cd-and-repo-workflow.md)
for CI/CD and release process.

## Architecture

11 services (api-gateway, mandate, catalog, shopping-agent, checkout, paypal-adapter, tracking,
resolution, triage-ai, audit, web) in one monorepo — see
[`.claude/prd/architecture/service-map.md`](.claude/prd/architecture/service-map.md) and
[`.claude/prd/architecture/overview.md`](.claude/prd/architecture/overview.md).

## License

MIT — see [`LICENSE`](LICENSE).
