# Zero-cost deployment research (as of 2026-10-10)

Labels: **V** = read on an official page today (URL given); **VC** = third-party/secondary; **I** = unverified/inference. Limits change; re-check before 2026-11-01.

## 1. Comparison table

| Service | Free limits | Sleep / cold start | Fit for us | Source |
|---|---|---|---|---|
| Render web service (free) | 750 instance-h/mo per workspace, no rollover, suspended when exhausted (V); 1 instance; ephemeral disk; no one-off jobs/shell; no SMTP ports 25/465/587 (V); may suspend on unusually high outbound traffic (V) | Spins down after 15 min without inbound traffic; wake ~1 min (V) | Best FastAPI host (Render is also a hackathon sponsor, see brief) | https://render.com/docs/free |
| Render background worker / cron | Page lists only web services, Postgres, Key Value, static sites as free-eligible; other types do not support Free (V) | n/a | NOT free. Use GitHub Actions schedule or in-process asyncio poller instead | https://render.com/docs/free |
| Render Postgres (free) | 1 GB, 1 per workspace, **expires 30 days after creation** (+14 day grace), no backups (V) | n/a | DO NOT use for the final demo (expires before/around judging) | https://render.com/docs/free |
| Render Key Value (free) | 1 instance, memory only, lost on restart (V) | n/a | Cache only | https://render.com/docs/free |
| Vercel Hobby | 200 projects, 100 deployments/day, 45 min build, 100 MB upload, 120 s proxied timeout (V); runtime logs kept 1 h (V); allotments per fair-use page (not read: I) | Serverless: cold starts on first call (magnitude I) | Next.js frontend: yes. Python functions: only for thin stateless endpoints; function duration/memory on Hobby not read (I) | https://vercel.com/docs/limits |
| Vercel cron (Hobby) | Once per day max, +/-59 min precision; over-frequent expressions FAIL the deploy (V) | n/a | Useless as keep-warm or poller | https://vercel.com/docs/cron-jobs/usage-and-pricing |
| Neon Free | 1 GB/project (100 projects), 100 CU-h/project/mo (~400 h at 0.25 CU), 10 branches, 5 GB egress, PITR 6 h; at limit compute suspends / writes fail, data not deleted (V) | Scale to zero after 5 min idle, cannot be disabled on Free (V); resume latency I (commonly sub-second to ~1-2 s, VC) | Best free Postgres for the demo. Connection limit not on plan page (I): use the pooled (-pooler) endpoint | https://neon.com/docs/introduction/plans |
| Supabase Free | 500 MB DB (shared CPU, 500 MB RAM), 50k MAU auth, 2 active projects, 5 GB egress, 1 GB files, 500k edge invocations (V) | **Pauses after 1 week inactivity** (V) | Fine as DB/Auth alternative; risk: paused project mid-review window. Need a weekly ping or a real query | https://supabase.com/pricing |
| Google Cloud Run | Commonly cited free tier 2M requests, 180k vCPU-s, 360k GiB-s, 1 GiB egress (I - page did not render; verify); needs billing account/card | Scale to zero; cold start seconds (I); min-instances=1 is billed (V in principle) | Good "real microservices" option but card + billing = cost cliff | https://cloud.google.com/run/pricing |
| Fly.io | **No free tier**; trial = 2 h machine runtime or 7 days, no card to start, card needed after (V) | n/a | Not zero-cost. Skip | https://docs.fly.io/about/pricing |
| Koyeb | Free instance 512 MB / 0.1 vCPU, 1 per org, Frankfurt/Washington (VC); scales down after 1 h no traffic (V per search summary of docs); Mistral acquired Koyeb Feb 2026 (VC); card requirement conflicting (VC) | 1 h idle sleep | Backup option for ONE service only | https://www.koyeb.com/docs/run-and-scale/scale-to-zero |
| Railway | One-time $5 trial credit for 30 days (V per docs summary), then Free plan with $1/mo credit (V) ; 5 services/project in trial | none while credit lasts | Credit runs out; not recommended | https://docs.railway.com/pricing/free-trial |
| Cloudflare Workers/Pages | Workers Free 100k req/day, 10 ms CPU/request, 5 cron triggers, 50 subrequests (V); Python Workers support not confirmed (I) | No cold-start sleep (I, edge isolates) | Use only for static frontend (Pages) or a tiny keep-warm pinger Worker (cron trigger). Not for FastAPI | https://developers.cloudflare.com/workers/platform/limits/ |
| GitHub Actions | Public repos: standard runners free (V); private Free plan: 2,000 min/mo; artifacts 500 MB, cache 10 GB; with no payment method usage stops at quota (V) | n/a | CI/CD + scheduled keep-warm (public repo is required anyway) | https://docs.github.com/en/billing/managing-billing-for-your-products/about-billing-for-github-actions |
| UptimeRobot Free | 50 monitors, 5-min interval (V); commercial use not stated (I) | n/a | 5-min ping beats Render 15-min sleep | https://uptimerobot.com/pricing/ |
| cron-job.org | Free, 1-min minimum interval, listed cap 60 executions/hour (V) | n/a | Backup pinger | https://cron-job.org/en/ |
| Grafana Cloud Free | 10k metric series, 50 GB logs, 50 GB traces, 14 d retention, 3 users, no card (V) | n/a | Logs/metrics (optional) | https://grafana.com/pricing/ |
| Sentry Developer | 1 user, 5k errors, 5M spans, 50 replays, 30-day retention (V) | n/a | Error tracking | https://sentry.io/pricing/ |
| Better Stack | Not checked (I) | | optional | |
| cloudflared quick tunnel | Free, no uptime guarantee, new hostname every run, 200 in-flight requests, no SSE (V) | | Local-dev webhooks / return URL only | https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/ |
| ngrok free | Not checked (I): random/one static domain, interstitial page possible | | Alternative to cloudflared | |

## 2. Free LLM options (for our ~3 AI calls: cart, intent-fit, triage/drafts)

| Provider | Free limit | Notes | Source |
|---|---|---|---|
| Gemini API free tier | Free models: Gemini 3.8/3.6/3 Flash, 2.5 Flash, 3.5/3.1/2.5 Flash-Lite (V). Exact RPM/RPD NOT on the docs page; only visible in AI Studio per project (V). Quotas per project, reset midnight Pacific (V). **Free-tier content is used to improve Google products (V)** | Use only seeded/synthetic data. Check AI Studio before demo | https://ai.google.dev/gemini-api/docs/pricing , https://ai.google.dev/gemini-api/docs/rate-limits |
| Groq free | gpt-oss-120b / gpt-oss-20b / qwen3.8-27b: 30 RPM, 1k RPD, 8k TPM, 200k TPD (V). 429 + retry-after | 8k TPM is tight for long prompts; fast. Good fallback | https://console.groq.com/docs/rate-limits |
| OpenRouter `:free` models | 20 RPM; 50 RPD if < $10 credits bought all-time, 1,000 RPD if >= $10 (V) | A one-time $10 top-up lifts the cap (small spend, not zero) | https://openrouter.ai/docs/api-reference/limits |
| Anthropic / OpenAI credits | Not checked (I). No assumed free credits | Do not rely | |

Plan: primary Gemini Flash-Lite, fallback Groq, then fail closed to HUMAN_REVIEW (matches brief). Provider-agnostic `LLM_PROVIDER` env var. Budget per demo run is small (a few calls) so RPD is not the issue; per-minute limits and 429 during judge parallel use are. Record a cached/"golden" response mode (labelled) as last resort. Load rough check: 20-prompt cart test = 20 calls, fits all limits (I).

## 3. Recommended stacks

### (a) Demo-hardened profile (fewest moving parts)
- Frontend: Next.js on Vercel Hobby (or Cloudflare Pages). Hobby is non-commercial by Vercel terms (I: not re-read) - hackathon use should be fine.
- Backend: ONE Render free web service running a modular monolith or an API gateway process with services as internal modules (FastAPI). One cold-start domain instead of N.
- DB: Neon Free (pooled endpoint). Audit log role/triggers work on Neon (standard Postgres; I - test the INSERT/SELECT-only role).
- Poller (late/lost detection): in-process asyncio task + a GitHub Actions scheduled call (hits `/internal/tick` with a secret) as a backup; the demo-clock control also triggers it manually.
- Keep-warm: UptimeRobot 5-min monitor on `/health/deep` (touches DB so Neon stays warm too) + cron-job.org as second pinger.
- LLM: Gemini Flash-Lite, Groq fallback.
- Monitoring: Sentry Developer + Render logs. Grafana optional.
- Cost: $0, no card needed on any (Render card only needed for overage; V: without a payment method, services are suspended rather than billed).

### (b) Fully separated services profile
- Each service (gateway/auth, mandate, agent, orders/PayPal, tracking/poller, policy/refund, audit, MCP) = its own Render free web service. Problem: **750 instance-hours per WORKSPACE** (V). One always-on service = ~730 h/month, so only ONE service can be kept awake all month. With 3+ services, hours exhaust early unless services sleep (sleep consumes no hours - I inference from "instance hours").
- Therefore: services sleep; gateway is pinged; downstream waking chains add ~1 min each (V) => a cold request through gateway -> 3 sleeping services could take 3+ min (I). Mitigation: warm-up script hitting every `/health` in parallel before any demo, and gateway fans out health checks.
- Alternative to dodge the cap: put services on mixed hosts - gateway+hot-path on Render, one service on Koyeb free (1 instance only, VC), the rest in Cloud Run (card needed, cost cliff). Not recommended; prefer (a) for the submitted demo and show (b) in architecture docs + a docker-compose profile that judges can run locally.
- Inter-service calls use public HTTPS URLs (free services cannot receive private network traffic; V).
- Recommendation: build (b)-ready code (separate FastAPI apps, one Dockerfile each, compose file), deploy the (a) topology by mounting the apps in one process. Decision for architecture agents.

## 4. Cold-start / sleep risk per service type + mitigations

| Component | Risk | Mitigation |
|---|---|---|
| Render API (15 min idle, ~1 min wake; V) | Judge's first click hangs ~60 s | UptimeRobot every 5 min (V interval) + cron-job.org; frontend shows "waking server" state + retry; pre-record video from warmed system |
| Neon (5 min idle suspend; V) | First query slow (I: ~1-2 s) | `/health/deep` pings DB every 5 min (also burns CU-h: 0.25 CU always-on ~730 h > 400 h budget, V math from plan page => compute would exhaust ~day 16!). Better: ping DB only during review windows or use pinger on API only and accept 1-2 s DB wake |
| Supabase (1 week idle pause; V) | Project paused | If used, weekly query via GitHub Action |
| Vercel functions | Cold start (I) | Keep Python off Vercel; frontend static/SSR only |
| LLM 429 | cart/triage fail | retry w/ backoff, provider fallback, fail closed |
| Render monthly hours (750; V) | Suspended until month end if exhausted | One always-on service + pinger = ~730 h: leaves almost no headroom. Do NOT also ping a second service 24/7. Stop pingers outside windows |

Warm-up script (before recording/submission): curl all `/health` (parallel), run `/health/deep`, run one full golden-path dry run (create mandate -> cart -> order create only), wait for 200 on each, then record within 10 min. Put in `scripts/warmup.sh`.

## 5. Webhook / return URL behaviour
- PayPal return_url/cancel_url: must point to the PUBLIC frontend/API URL (e.g. `https://<app>.onrender.com/api/paypal/return`). Not yet tested end-to-end (brief: I). Test in week 1.
- If the API is asleep at redirect time the buyer waits up to ~1 min on a blank page (V sleep behaviour): ping just before the approve click; return page should be a static Vercel route that calls the API with retry.
- Webhooks are hint only (poll authoritative). Receiver URL = Render public URL; sandbox webhooks hitting a sleeping service may time out -> design is already poll-first (V brief).
- Local dev: `cloudflared tunnel --url` (V: free, random URL each run, no SLA) or ngrok (I). Update return URL via env var each run.
- Preview deployments get different URLs: return URL must come from env, never hardcoded.

## 6. Secrets / env vars
- Free secret stores: Render environment variables / secret files, Vercel env vars (scoped Production/Preview), GitHub Actions encrypted secrets (all I for exact features; standard). Doppler/Infisical free tiers not checked (I).
- Rules: `.env.example` only in repo; real values in platform dashboards; gitleaks in CI + pre-commit; separate sandbox PayPal creds; HMAC key, DB URL, LLM keys, `INTERNAL_TICK_SECRET` never in client bundle (only `NEXT_PUBLIC_*` public).
- Vercel Hobby runtime logs kept only 1 h (V): do not rely on them for audit; our audit log is in the DB.
- Render free service has no shell (V): include admin/debug endpoints behind secret instead.

## 7. Custom domain / HTTPS
- Render gives `*.onrender.com` HTTPS and Vercel `*.vercel.app` HTTPS automatically (I standard; not re-read). Custom domains are optional; a domain costs money (non-zero) - skip; use free subdomains. Free DNS alternatives (e.g. is-a.dev, DuckDNS) not verified (I).
- CORS: allow exact frontend origin(s) via env var.

## 8. Cost cliffs and spend guards
- Render: no payment method on workspace => suspend instead of bill (V). Do NOT add a card; if added, bandwidth/build overage bills (V). Free Postgres expires at 30 days (V) - use Neon.
- Render 750 h cap shared per workspace (V): a second always-on service silently suspends all free services at month end.
- Neon: compute exhaustion suspends compute until next period; storage limit makes writes fail; no deletion (V). No card = no charge (I).
- Vercel Hobby: usage beyond allotment pauses/limits rather than charging (I); do not upgrade to Pro/add spend (on-demand charges apply on Pro, V).
- Cloud Run: needs billing account; set budget alerts + `--max-instances=1`, no min-instances (I). Prefer to avoid.
- Fly.io: free only 2 h/7 days (V); card required afterward. Avoid.
- OpenRouter: a $10 top-up is a deliberate spend; set low key limit (I).
- Gemini: free tier has no spend; if the project is linked to billing, paid tier applies (I) - keep a billing-free Google project.
- GitHub Actions: with no payment method, usage stops at quota (V); keep repo public (free); scheduled workflows in public repos disabled after 60 days of repo inactivity (I - well known, unverified today).
- Guards: no cards where avoidable; one account owner; calendar reminder 2026-11-01 to re-check every limit; usage dashboards weekly.

## 9. CI/CD
- GitHub Actions per-service: path-filtered workflows (`paths: services/<name>/**`): ruff + pytest + gitleaks + pip-audit; on main, deploy via Render Deploy Hook URL stored as secret (hook calls are I-standard) or Render auto-deploy from GitHub; Vercel auto-deploys the frontend from Git.
- Preview environments: Vercel preview per PR (V that Vercel supports deployments up to 100/day on Hobby). Render PR previews are I (likely paid); use a single staging branch/service instead.
- Concurrency group per service to avoid parallel deploy; health-gate step: after deploy, `curl --retry` on `/health` (accounts for 1-min wake) else fail and roll back by redeploying previous commit (manual `workflow_dispatch` with SHA input).
- Scheduled workflow `keepwarm.yml` (cron */10) as third pinger; counts against nothing on a public repo (V).
- Uptime check of the repo itself: run `scripts/warmup.sh` in a nightly workflow near submission.

## 10. Per-service placement table (TEMPLATE - other agents fill)

| Service | Responsibility | Profile (a) host | Profile (b) host | Sleeps? | Cold-start budget | DB / schema | Public URL needed? | Secrets | Health endpoint | Keep-warm? | Owner agent |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gateway/auth | | Render #1 | Render | | | | yes | | /health | yes | |
| mandate | | in #1 | | | | | no | | | | |
| agent (LLM) | | in #1 | | | | | no | | | | |
| orders/PayPal | | in #1 | | | | | return_url | | | | |
| tracking/poller | | in #1 | | | | | no | | | | |
| policy/refund | | in #1 | | | | | no | | | | |
| audit | | in #1 | | | | | no | | | | |
| MCP server | | in #1 | | | | | maybe | | | | |
| frontend | | Vercel | Vercel | no | | | yes | NEXT_PUBLIC only | | | |
| database | | Neon | Neon | yes (5 min) | | | no | DATABASE_URL | | | |

## 11. What breaks first under demo load (ranked)
1. Cold start of the Render API on first judge click (~1 min; V).
2. LLM 429 (Groq 8k TPM, 30 RPM; OpenRouter free 20 RPM / 50 RPD; Gemini quotas unknown without AI Studio; V) when several judges click at once.
3. Render 750 h exhaustion if more than one service is kept alive or a pinger runs on several services (V).
4. Neon compute hours: 24/7 DB pings exhaust ~400 h at 0.25 CU in about 16 days (math from V figures); also 5 GB egress (V).
5. Sleeping chain in profile (b): N services x ~1 min.
6. PayPal sandbox flows (real approve click, India-based account/buyer constraints from brief) and token expiry (~9 h; V brief).
7. Single instance, ephemeral disk (V): no local file state; all state in Neon.
8. Render suspension for "unusually high outbound traffic" (V) - avoid tight polling loops against PayPal/LLM.
9. Supabase pause after a week idle (V) if used.
10. Free-tier Gemini content used to improve products (V): only synthetic data, state this in README.

## 12. Open items / unverified
- Vercel Hobby function duration/memory, fair-use allotments (I). Better Stack, ngrok, Doppler (I). Cloud Run free tier page failed to render (I). Neon connection limit and resume latency (I). Render PR previews on free (I). Gemini exact RPM/RPD (read in AI Studio). Anthropic/OpenAI credits (I).
- Real return URL through Render and webhooks not yet tested (brief).
- Conflict to note: brief says Render is a sponsor prize; deploying the demo on Render supports that prize but the "one sponsor prize per project" rule still applies.
