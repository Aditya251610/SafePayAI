# web - Deployment (Vercel zero-cost)

Labels: V verified (read on an official page per deployment-zero-cost.md), VC vendor claim, I inference/unverified. Source: deployment-zero-cost.md sec 1/5/6/7, auth-gateway.md sec 2.3, prd.md sec 6/REQ-WB-001/055.

## 1. Platform and topology
- `web` deploys to Vercel Hobby (REQ-WB-001/055). Vercel Hobby limits (V, deployment-zero-cost.md sec 1): 200 projects, 100 deployments/day, 45 min build, 100 MB upload, 120 s proxied timeout, runtime logs kept 1 h.
- `web` is a Next.js (TypeScript) static/CSR app with no server-side rendering of authenticated data (prd.md sec 4 non-goal) - keeps Python/stateful work off Vercel entirely (deployment-zero-cost.md sec 4: "Keep Python off Vercel; frontend static/SSR only").
- Gateway (api-gateway) runs on Render; cookie topology requires same registrable domain to keep `SameSite=Lax` working across the browser-gateway hop (auth-gateway.md sec 2.3 cross-site hosting caveat; R2 in prd.md sec 7). Preferred: Vercel rewrite of `/api/*` to the Render gateway URL, so the browser only ever talks to the Vercel origin (REQ-WB-001: "talks only to the gateway via same-origin `/api/*`").

## 2. Preview deploys
- Every PR gets a Vercel preview deployment (V: Vercel supports up to 100 deployments/day on Hobby, deployment-zero-cost.md sec 9).
- Previews get a different origin per deployment -> Origin/CSRF checks and the PayPal return URL (which must be a fixed, env-driven value, deployment-zero-cost.md sec 5) would fail if pointed at a real backend session (R9 in prd.md sec 7).
- Decision (per R9 mitigation options): previews run `API_MODE=mock` by default with a visible "PREVIEW - MOCK API" banner (MSW-style mocks generated from the committed OpenAPI contract, REQ-WB-058; never shipped in the production build, R5). Only the `main`-branch deployment (production/staging alias) talks to the real hosted gateway.
- If a specific preview needs to test against the real gateway (rare, e.g. a gateway-contract spike), the gateway's CORS/Origin allowlist can be extended with an explicit per-preview-URL pattern as a deliberate, logged exception - not the default.

## 3. Environment variables (names only; see spec.md sec 13 for the client-exposed subset)
| Name | Scope | Exposed to client | Set per |
|---|---|---|---|
| `NEXT_PUBLIC_PS_WEB_DEMO_MODE` | Production, Preview | yes | environment |
| `NEXT_PUBLIC_PS_WEB_PAYPAL_APPROVE_HOST_ALLOWLIST` | Production, Preview | yes | environment |
| `PS_WEB_GATEWAY_INTERNAL_URL` | Production only (rewrite target) | no | environment |
| `PS_WEB_API_MODE` (`live` \| `mock`) | Production=`live`, Preview=`mock` default | no | environment |
| `PS_WEB_SENTRY_DSN` | Production (optional) | no | environment |
- Rule (deployment-zero-cost.md sec 6): `.env.example` only in the repo; real values live only in Vercel's dashboard, scoped Production/Preview; gitleaks in CI and pre-commit catches accidental commits; no `PAYPAL_*`, HMAC, JWT, or DB values ever belong to `web` (web owns no secrets, service-map.md sec 2 "web... Owns: nothing").
- Vercel Hobby runtime logs are kept only 1 h (V) - never rely on them for audit; the audit trail of record is the `audit` service's DB-backed chain, not frontend logs.

## 4. Cookie, CORS, and domain implications (gateway on Render)
- Cookie: `__Host-` prefixed, httpOnly, Secure, `SameSite=Lax` session cookie is minted by the gateway (auth-gateway.md sec 1). For it to reach the gateway on every `/api/*` call made from the Vercel-hosted page, the browser must see `/api/*` as same-origin - achieved via Vercel's rewrite feature (not a redirect) proxying `/api/*` to the Render gateway URL server-side.
- If the rewrite approach is dropped and the browser calls the Render origin directly, the cookie becomes third-party and `SameSite=Lax` breaks (auth-gateway.md sec 2.3, R2) - this is explicitly the non-preferred fallback, not a parallel supported mode.
- CORS: only needed as a fallback if the direct-origin mode above is ever used; in the preferred rewrite topology the gateway sees same-origin requests and no CORS preflight is needed for the primary flow. If CORS is configured as a safety net, it must allow the exact Vercel production origin(s) only, `Access-Control-Allow-Credentials: true` paired with an exact origin (never `*`), per auth-gateway.md sec 2.3.
- Return URL (PayPal sandbox redirect target): must be the gateway's public Render URL or a same-origin `/api/*`-proxied path on the Vercel domain, sourced from env, never hardcoded (REQ-WB-027 constraint, prd.md sec 6, deployment-zero-cost.md sec 5). Preview deployments must not be used as a live PayPal return target (section 2 above - mock mode avoids this entirely).
- Security headers relevant to `web`: `Referrer-Policy: no-referrer` (the PayPal `token` param appears in URLs, auth-gateway.md sec 2.3), CSP with no inline script, `X-Content-Type-Options`, `frame-ancestors none`. Next.js config sets these; not a Vercel-platform default to assume.

## 5. Cold start interaction (frontend side only; backend cold start owned by deployment-zero-cost.md sec 4)
- Vercel serverless functions (if any API routes are used purely as the rewrite/proxy layer) have their own cold start (I, not measured) - keep any Vercel-side function thin (pure proxy/rewrite, no business logic) so this is not compounded with the Render gateway's ~1 min wake (V, deployment-zero-cost.md sec 4).
- `web` never pings the DB or any backend service on a schedule itself; keep-warm pinging (UptimeRobot/cron-job.org on `edge`) is the backend's responsibility (deployment-zero-cost.md sec 4/9) - `web` only issues a single background warm-up call on landing-page load (spec.md sec 12), which is a normal user-triggered request, not a scheduled poller (avoids Vercel Hobby cron limits: once/day max, useless as a keep-warm mechanism, deployment-zero-cost.md sec 1).

## 6. Rollback
- Vercel's deployment model keeps every previous deployment addressable; rollback = re-promote the last known-good production deployment via the Vercel dashboard or CLI (`vercel rollback` / promote a prior deployment to the production alias) - no rebuild required, near-instant (I, standard Vercel behavior, not re-verified against a dated doc page today).
- Procedure for this project: (1) identify the last commit SHA that passed the S-sprint's hosted smoke test (sprint-plan.md "Deploy ritual"); (2) promote that deployment to production in the Vercel dashboard; (3) re-run `scripts/warmup` against the now-current production alias; (4) confirm `/about` and the receipt screen render (smoke); (5) log the rollback in the sprint log with reason and commit SHA.
- Because `web` holds no database and no migrations, rollback is pure code - it cannot desynchronize from the backend's own schema state, but it CAN desynchronize from the backend's current OpenAPI contract if the backend has moved ahead; REQ-WB-058's zod runtime validation with graceful unknown-field tolerance is the safety net for an old frontend talking to a newer, additive-only backend (ADR-008).
- No custom domain is used (free `*.vercel.app` subdomain, deployment-zero-cost.md sec 7) - rollback never involves DNS.

## 6a. Vercel implications of the Framer Motion / WebGL / Aceternity UI decision
- Bundle size: WebGL/three.js-class libraries and Aceternity's canvas-heavy components add meaningfully to client JS weight. Vercel Hobby's 100 MB upload cap (sec 1, V) is generous relative to this risk, but the practical limit is cold-start/parse-time on first paint, not the upload cap itself (I) - code-split so only the landing route's bundle pays this cost (tech-stack.md sec 3.2 T2; spec.md sec 10 WHERE rule). Money-path routes (mandate sign, cart/checkout, receipt, offer/approve, audit, human-review) must not import these packages at all, so their bundles stay small and fast regardless of what the landing page does.
- No additional CDN/asset hosting is currently planned for 3D assets: the WebGL/Aceternity usage described here is confined to code-driven canvas effects (shaders/generated geometry), not large downloaded 3D model files (.glb/.gltf) or textures. If implementation later adds such binary assets, they should go through Vercel's own static asset pipeline/CDN (no separate host needed) - revisit this note if that changes, since large binary 3D assets would reintroduce the 100 MB upload cap and build-time budget (45 min, sec 1) as real constraints.
- Day-14 cut line interaction (sprint-tasks.md): the cut line's required buyer-core-flow screens (mandate sign -> cart -> PayPal handoff -> return -> receipt) are, by the spec.md sec 10 WHERE rule, already in the "plain shadcn + light Framer Motion only" set - they carry zero WebGL/Aceternity weight by design. The Day-14 line is therefore a floor that holds regardless of whether the landing-page WebGL/Aceternity work ships at all; that work is explicitly late/cuttable (sprint-tasks.md) and never competes with or blocks the cut line's scope.

## 7. Open items / conflicts
- Exact initial-timeout and give-up thresholds for the "waking up" UI (spec.md sec 12) are implementation-tuned, not specified here - no invented number.
- R9's mock-preview approach assumes MSW-generated mocks stay strictly dev/preview-only and are tree-shaken out of the production bundle; this must be verified by a build-output check in CI (test-plan.md references this), not assumed from this doc alone.
- If tech-stack.md is added later and specifies a different hosting target for `web` than Vercel, this file must be re-synced; ADR-002/ADR-009 and REQ-WB-001/055 are the current source and all agree on Vercel.
