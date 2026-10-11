# web

SafePayAI's only UI (Next.js, App Router, TypeScript). Two route groups,
`(buyer)` and `(merchant)`, plus a public landing/about area. Owns no data and
no authorization logic - it displays server decisions from `api-gateway` via
a same-origin `/api/*` rewrite and never recomputes money, mandate, or policy
state client-side. See `.claude/prd/services/web/{prd,spec}.md` for full
requirements.

This is a **Wave 4 skeleton**: routes, layout, and config exist; screens
render mock/placeholder data clearly commented as such. No real gateway calls
are wired yet (`lib/api-client.ts` stub functions are marked `TODO Wave 5`).

## Stack

Next.js + TypeScript + shadcn/ui (baseline everywhere) + Framer Motion +
WebGL/Aceternity UI (landing page only - see `app/page.tsx`). Money-path
screens (mandate sign, PayPal handoff, receipt, refund offer, audit log,
human-review) stay plain shadcn/ui + light Framer Motion only, per
`tech-stack.md` sec 3.1-3.2 and `spec.md` sec 10.

## Dev commands

```bash
pnpm install
pnpm dev          # http://localhost:3000
pnpm build        # production build
pnpm start        # run the production build
pnpm lint         # eslint
pnpm typecheck    # tsc --noEmit
pnpm test         # vitest (component/unit)
pnpm test:e2e     # playwright (e2e/a11y)
pnpm format       # prettier --write
```

## Honesty rules (non-negotiable, enforced by lint/tests)

- Persistent, non-dismissible SANDBOX banner on every page.
- SIMULATED / CACHED / ILLUSTRATIVE labels wherever that kind of data
  appears.
- No "PayPal-backed/verified/protected" or similar banned claims (see
  `spec.md` sec 5) - enforced by source lint and a runtime crawl test.
- `dangerouslySetInnerHTML` is banned (`react/no-danger` ESLint rule).

## How we use AG Grid (sponsor-prize candidate)

Not yet implemented in this skeleton (Wave 4). Will be Community-edition-only
(sort, filter, pinning, custom cell renderers, CSV export) across exactly
three screens: merchant orders table, human-review queue, audit log - see
`spec.md` sec 9.
