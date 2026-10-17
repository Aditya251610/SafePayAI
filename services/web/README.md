# web

SafePayAI's only UI: Next.js (App Router), TypeScript, Tailwind. It owns no data and makes no
decisions. It shows what `api-gateway` returns, through a same-origin `/api/*` rewrite, and never
computes money, mandate or policy state in the browser.

Routes follow the buyer journey and the four roles:

| Area               | Routes                                                                                                                                                                                                                 |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Public             | `/`, `/login`, `/states` (not served in production)                                                                                                                                                                    |
| Buyer              | `/home`, `/mandate/new`, `/mandate/[id]`, `/intent`, `/agent/[proposal_id]`, `/cart/[id]`, `/checkout/return`, `/checkout/cancel`, `/orders`, `/orders/[id]`, `/orders/[id]/report`, `/cases/[id]`, `/approve/[token]` |
| Any signed-in role | `/audit`                                                                                                                                                                                                               |
| Merchant, operator | `/merchant`, `/merchant/cases/[id]`                                                                                                                                                                                    |
| Operator           | `/ops`                                                                                                                                                                                                                 |
| Reviewer           | `/review` (read-only)                                                                                                                                                                                                  |

## Run

```bash
pnpm install
cp .env.example .env.local        # set PS_WEB_GATEWAY_INTERNAL_URL to a running gateway
pnpm dev                          # http://localhost:3000
```

| Command                                              | What it does                                                                                                                  |
| ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `pnpm lint` / `pnpm typecheck` / `pnpm format:check` | static checks                                                                                                                 |
| `pnpm test` / `pnpm test:coverage`                   | unit and component tests (MSW answers every `/api` call)                                                                      |
| `pnpm test:e2e`                                      | Playwright against the built app, with `/api` answered by route handlers; set `PW_CHROMIUM_PATH` to use an installed Chromium |
| `pnpm build` then `pnpm check:bundle`                | production build, then the per-route JavaScript budget (180 KB gzip)                                                          |

## Layout

```
app/            routes, layouts, fonts (app/fonts)
components/     ui primitives, shell, and screen components
lib/api/        the only way to reach the backend (see below)
lib/auth/       session, roles, navigation, safe redirects
lib/format/     display-only money, date and label helpers
lib/honesty/    banned claims and disclosure text
styles/         design tokens (the only place a colour value appears)
tests/          unit, e2e, and test-only mocks and fixtures
```

## API layer (`lib/api`)

- One base URL, `API_BASE_URL` in `lib/api/config.ts`. Every path is relative to it.
- Each non-GET call fetches a fresh single-use CSRF token first, and routes that need it get an
  `Idempotency-Key`. A rejected token is retried once with a new token and the same key.
- Idempotent reads are retried while the backend wakes up. Posts never are.
- A timeout or dropped connection on a money route is an `AmbiguousOutcomeError`: screens read the
  real state back instead of posting again.
- Every response is checked against a zod schema; every error is reduced to `{ code, message,
requestId }` whatever shape the owning service used.

## Rules the tests enforce

- No raw `fetch` outside `lib/api`; no arithmetic on `*_minor` values; no colour literals outside
  `styles/tokens.css`; no `dangerouslySetInnerHTML`.
- No banned claims in source or in rendered text of any screen, in either theme.
- Sandbox banner and footer disclosure on every page; simulated carrier data is always labelled.
- Dark and light themes, phone, tablet and desktop layouts, and no serious accessibility findings
  on any screen.

## Known gaps on the backend side

The web app works around these without touching the backend: the gateway does not forward request
bodies for mandate revoke, offer accept, approval consent and the demo shipment force route; the
case read route returns no offer; there is no reviewer decision route and no seeded reviewer
account. See `contracts/frontend-integration-contract.md`.
