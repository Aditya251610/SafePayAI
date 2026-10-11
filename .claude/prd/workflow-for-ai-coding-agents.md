# Workflow: one human directing Claude Code to build SafePayAI in ~30 days

Labels: V verified, VC vendor claim, I inference/assumption. Sources: `00-context-brief.md`, `architecture/{overview,service-map,adr,deployment-zero-cost}.md`.
Dates: Day 1 = 2026-10-10. Day 14 = 2026-10-23 (cut line). Day 28 = 2026-11-06 (freeze). Target submit 2026-11-10 (day 32). Deadline 2026-11-12 noon PT (VC, re-read Devpost rules).

## 0. Operating principles
- Human is the bottleneck, not agent output. Plan around human review hours (I: ~4-6 h/day), not code volume.
- Docs are the source of truth; code conforms to docs; contracts conform to docs; tests conform to contracts.
- Money path (mandate, catalog prices, checkout, paypal-adapter, resolution, api-gateway) gets human line-by-line review. Everything else gets spot review.
- Every agent starts from a context pack, not from the whole repo. Small context = fewer hallucinations.
- Never put secrets in prompts, docs, or memory. Never read or print `.env`. PayPal creds live only in paypal-adapter platform env.
- Agents never merge to `main`. Only the human merges `integration` -> `main`.

## 1. Phases (tied to the cut lines)
| days | goal | exit gate |
|---|---|---|
| 1-3 | Contract phase: OpenAPI + event schemas + libs skeleton + compose + CI | All 10 specs + event schemas committed; CI contract-diff check green; stubs boot in compose |
| 3-5 | Stub phase: each service returns canned valid responses | Golden path runs end to end on stubs (click-through) |
| 5-14 | Implement the CORE loop: mandate -> cart check -> PayPal order/capture -> tracking late -> case -> offer -> refund -> audit | DAY-14 CUT LINE: golden path works on sandbox, hosted or compose, with real PayPal approve click and real refund |
| 15-21 | Hardening: AI services, intent-fit, approval links, reconcile, security audit, Profile B hosting, warm-up | Hosted Profile B golden path green 3 days in a row |
| 22-28 | Polish: UI, labels (SIMULATED CARRIER), README, demo script, video rehearsal | DAY-28 FREEZE: only bug fixes, docs, video |
| 29-32 | Record video, README, Devpost text, submit 11-10 | Submitted; 2 days buffer |

Day-1 prerequisites: real return URL into our own server, refund PENDING, LLM cart reliability (>=95% valid on 20 prompts) are all untested (brief section 3, I). Schedule spikes in days 1-5, in the paypal-adapter and shopping-agent worktrees. Failure of a spike triggers a scope decision at day 5, not day 20.

## 2. Parallel split: worktrees, one agent per service
- Layout per ADR-009 monorepo. Service ownership = directory ownership: `services/<slug>/**` plus its `contracts/openapi/<slug>.json` and its produced `contracts/events/*`.
- One git worktree per service, one branch per service: `git worktree add ../ps-<slug> -b svc/<slug> integration`.
- Max concurrent agents: 3-4 (I; human review capacity is the limit). Order by dependency, not by "all at once".
- Wave plan:
  - Wave 1 (contracts, serial, human-reviewed): Software Architect / Backend Architect agent writes all OpenAPI + event JSON Schemas + `libs/common` (token verify, outbox, logging). Human reviews every spec (this is the cheapest review you will ever do).
  - Wave 2 (stubs, parallel, low risk): one agent per service generates stubs from specs. Use `/scaffold` skill. Stubs return canned valid payloads and pass contract tests.
  - Wave 3a (money core, parallel x3): mandate, paypal-adapter, catalog. These have no sync downstream dependency (service-map graph).
  - Wave 3b: checkout (needs 3a stubs/real), tracking, audit.
  - Wave 3c: resolution (largest, depends on most), then web in parallel with 3b/3c using stubs of the gateway.
  - Wave 4: shopping-agent, triage-ai (non-money; only after core golden path works, so day 14 does not depend on LLMs. Fallback paths: manual cart, HUMAN_REVIEW).
- Agent type per work (from `.claude/agents`):
  - Contracts: Software Architect, Backend Architect.
  - Service impl: Backend Architect (default); Senior Developer only for web.
  - paypal-adapter, resolution: Backend Architect + Security Architect consult up front.
  - DB, schemas, grants: Database Optimizer.
  - CI, compose, hosting, warm-up: DevOps Automator.
  - Branching hygiene: Git Workflow Master (rare use).
  - Tests: API Tester (contract and integration).
  - Review: Code Reviewer, AI-Generated Code Security Auditor, Application Security Engineer.
  - Gate: Reality Checker for day-14 and day-28 sign-off (defaults to NEEDS WORK).
  - Multi-agent coordination issues: Multi-Agent Systems Architect.
- Shared-file rule: agents may NOT edit `contracts/**` of another service, `libs/**`, `docker-compose.yml`, or `docs/` outside their lane. If they need a change, they write `CONTRACT_CHANGE_REQUEST.md` in their worktree root and stop that item. Human or the contracts agent applies it on `integration`, everyone rebases.
- `libs/` holds no business logic (ADR-009). Reviewer rejects any domain rule in `libs/`.

## 3. Contract-first sequence (per service)
1. Spec exists in `contracts/openapi/<slug>.json` (reviewed, merged to `integration`).
2. Event schemas for every event the service emits or consumes exist (`contracts/events/<name>.v1.json`), envelope per overview section 7.
3. Stub passes: schemathesis-style or pytest contract test hits every route and validates against the spec.
4. Implementation replaces stub route by route; contract test must stay green at every commit.
5. After implementation: regenerate OpenAPI from FastAPI; CI diff against committed spec must be empty. A diff means the code drifted: fix code, or file a contract change request (never silently update the spec to match drifting code).
6. Typed clients in `libs/clients` are GENERATED from specs, never hand-written. Agents must call other services only through them (no ad hoc `httpx` URLs).
7. Additive-only changes within `v1`. Breaking change = human decision, new version, all consumers updated same day.

## 4. Context pack (what each service agent receives)
Build one file per service at `docs/context-packs/<slug>.md` (assembled by the human or an agent; excerpts, not whole docs):
- Service-map section for this slug (role, owns, exposes, consumes, events, NOT its job).
- Relevant overview flows (F1-F5 rows touching this service), failure-mode rows, rules R1-R4.
- Relevant ADRs (always ADR-002, 003, 004, 006, 008; plus 007 / 010 / 011 where relevant).
- Its OpenAPI spec and event schemas (paths, not pasted).
- Brief section 3 verified PayPal facts (only for paypal-adapter, checkout, resolution, tracking) and section 5 honesty rules (all).
- Consumers' expectations: contract tests of those consumers (paths).
- Definition of done (section 5).
- Do-not-touch list.
- Rule: if a fact is not in the pack or specs, the agent must ask or mark `TODO(verify)`; it must not guess.

## 5. Prompt template for a service-building agent
```
ROLE: You are the <agent type> building ONE service: <slug> in repo safepayai. Worktree: ../ps-<slug>, branch svc/<slug>.

READ FIRST (in order, nothing else until done):
1. .claude/memory/index.md (load only entries matching tags: <slug>, paypal, <topic>)
2. docs/context-packs/<slug>.md
3. contracts/openapi/<slug>.json and contracts/events/* listed in the pack
Do NOT read .env or any secret. Do NOT browse the whole repo.

TASK: <one slice, e.g. "implement POST /mandates/{id}/evaluate with the 6 hard checks"> Replace stub behavior route by route.

INPUTS: spec paths, pack path, brief section 3 (verified PayPal facts) if PayPal is involved.

DEFINITION OF DONE (all must be true, report evidence for each):
- [ ] All routes in the spec implemented; contract test green; regenerated OpenAPI == committed spec.
- [ ] Unit tests for every rule/branch; failure-mode table rows for this service have a test (fail closed).
- [ ] Money-path code: integer minor units only; no float; server derives merchant/amount/currency/capture_id.
- [ ] Outbox row written in the same transaction as state change; consumers dedupe on event_id.
- [ ] Mutating endpoints honor Idempotency-Key.
- [ ] Internal token verified (aud = this service, deny by default).
- [ ] ruff + pytest + gitleaks + pip-audit pass locally.
- [ ] Service README updated (run, env vars by name only, endpoints, known gaps).
- [ ] Handoff note written (see section 9).

CONSTRAINTS:
- Stay inside services/<slug>/**. Need anything else? Write CONTRACT_CHANGE_REQUEST.md and stop that item.
- No new dependency without listing it and why in the PR description.
- No endpoint, field, event, or env var that is not in the spec or pack. If you think one is needed, request it.
- Every PayPal call must cite its source: a brief section 3 fact, or be marked `# UNVERIFIED-PAYPAL: needs live-sandbox check` and be unreachable from the golden path until checked. Do not invent PayPal fields, statuses, or error codes.
- LLM output is untrusted data: schema-validate; any failure maps to the restrictive default.
- Do not claim anything on the brief section 5 "Do NOT claim" list in code comments, UI strings, or README.

SECURE-CODING PREAMBLE (applies to everything you write):
- Parameterized queries only; no string-built SQL. Validate all input with Pydantic strict models; reject unknown fields.
- No secrets in code, logs, tests, fixtures, or error messages. Config from env by name; update .env.example with names only.
- Authz on every route: verify internal JWT (aud, exp, jti), check role. Never trust client-supplied amounts, merchant, currency, capture_id, or user id.
- Treat free text, catalog text, carrier notes, and LLM output as hostile (prompt injection; no tool use from it; no logging of raw secrets).
- Constant-time compare for HMAC/tokens; single-use tokens bound to proposal_hash; no PII beyond seeded demo data in logs.
- Timeouts on every outbound call; retries only on idempotent calls; money calls only with persisted PayPal-Request-Id (R3, R4).
- Errors: generic to client, detail to JSON log with trace_id.
- Pin dependencies; no `eval`, `pickle`, `shell=True`, or open CORS.

DO NOT TOUCH: contracts/** (other services), libs/**, docker-compose.yml, .github/**, docs/** (except your README and context-pack TODO comments), other services/**, .env*, main/integration branches.

PROCESS:
1. Plan in <=10 bullets, then implement. 2. Self-check against the DoD and the spec; list deviations. 3. Run tests. 4. Commit small, conventional commits on svc/<slug>.
FINAL REPORT (max 200 words): what is done, DoD evidence, deviations, open questions, UNVERIFIED-PAYPAL markers, files changed outside lane (should be none).
```
- One slice per prompt (one to three endpoints). Long omnibus prompts drift. Re-prompt per slice, same pack.
- Subagents inside an agent are not needed; the human is the orchestrator. Keep the tree flat (one level).

## 6. Review loop (every PR to `integration`)
1. Agent self-check (in prompt): DoD checklist with evidence, spec diff empty, deviations listed.
2. Automated gates (CI, required): ruff, mypy (money-path packages), pytest, contract tests, OpenAPI diff, gitleaks, pip-audit, migration up/down.
3. Reviewer agent, fresh context, never the author:
   - Code Reviewer: correctness, fail-closed behavior vs failure-mode table, idempotency, transaction boundaries, layering.
   - AI-Generated Code Security Auditor: secrets, authz gaps, injection sinks, missing RLS/grants, SSRF, prompt-injection paths. Run on every PR touching api-gateway, paypal-adapter, resolution, audit, and any AI service. Scan, fix, rescan; findings CWE-mapped.
   - Application Security Engineer / Security Architect: one pass at day 10 and day 20 on the whole money path, not per PR.
   - Reviewer prompt includes the spec and pack, and asks for a verdict: BLOCK / FIX / OK with file:line findings. It must also list "claims in code or strings that the brief forbids".
4. Human review, risk-weighted:
   - Money-path code: read every changed line. Checklist: integer minor units; server-derived values; persisted Request-Id before call; 409/timeout -> UNKNOWN not retry; 9 refund checks in order; hard block never overridden by AI; revoked mandate blocks at use time via sync call; no float; no amount from LLM or client.
   - Everything else: read spec diff, tests list, reviewer verdict; sample 1-2 files.
   - Time-box: 20 min per money-path PR, 5 min otherwise (I). If a PR needs more, it was too big: send back to split.
5. Merge to `integration` only when 1-4 pass. Squash or rebase; no merge commits from agents.
6. Reality Checker at gates (day 14, day 28): demands evidence (recorded run, logs, sandbox ids), default NEEDS WORK.

## 7. Integration cadence
- Daily: one `integration` branch. At a fixed time (evening, before the demo-readiness run) human merges all green `svc/*` branches into `integration`, then runs compose.
- Mid-day mini-rebase: agents rebase their worktree on `integration` before each new slice.
- Gate on every merge: contract tests (producer vs spec; consumer vs generated client), compose smoke (all `/readyz` green), golden-path script on stubs/real.
- Contract tests are the gate, not unit tests. A red contract test blocks all merges until fixed; the owner of the producer fixes it.
- `integration` -> `main` only when: golden path green on compose, no open BLOCK findings, docs sync done (section 8). From day 15, also deploy to Profile B staging after each `main` merge.
- Never leave a service broken on `integration` overnight; revert the merge instead.
- Profile A (compose) stays runnable always; Profile B hosts (`hosts/*.py`) are exercised in CI starting day 15 (I: mount smoke test).

## 8. Docs and code sync
Principle: docs lead. A behavior change starts as a doc/contract change.
| artifact | owner (who edits) | agents may |
|---|---|---|
| `00-context-brief.md`, `architecture/*`, PRD docs | human (or Software Architect agent on explicit instruction) | propose via change request only |
| `contracts/openapi`, `contracts/events` | contracts agent / human | never edit others'; may edit own after approved request |
| `docs/context-packs/<slug>.md` | human regenerates when specs/ADRs change | read only |
| `services/<slug>/README.md` | service agent | edit |
| `docs/DECISIONS-LOG.md` (new decisions made during build) | human | propose |
| `README.md` (root), demo script | human + one writer agent, days 22+ | draft |
- Rules:
  - New ADR or changed behavior -> update the architecture doc and context packs the same day, before more code is written against it.
  - Spec change -> bump generated clients, notify consumer worktrees (rebase).
  - Weekly (days 7, 14, 21, 28): Software Architect agent runs a "doc vs code vs spec" audit: lists divergences; human decides which side is right.
  - When code is right and doc is wrong, fix doc and note in decisions log; never leave both.
  - Label discipline: new facts get V / VC / I; anything PayPal-related V only if it came from the sandbox spike or a re-run.
  - Open items from overview section 10 (revoke semantics for captured orders, free-tier limits) are tracked in the decisions log with an owner and due day.

## 9. Handoff and memory hygiene
- Handoff (`/handoff` skill, saved to `.claude/handoff/handoff-YYYY-MM-DD-HHmm.md`):
  - Write at end of each working day AND whenever an agent session ends mid-slice or context gets long.
  - Contents: goal/status, files changed, decisions, failing tests/blockers, exact next steps, suggested skills. Reference PRD/specs by path; never duplicate them. No secrets.
  - Session start: load newest handoff if < 48 h (session-startup rule), then memory index, then context pack.
  - Per-service handoff is the agent's final report, pasted into the PR description.
- Memory (`.claude/memory`, `index.md` + `entries/`):
  - Store: durable decisions, corrections, verified sandbox facts, recurring agent mistakes ("agents invented field X"), tags precise (service slug, topic).
  - Do not store: status, TODOs, code summaries, anything derivable from the repo, secrets, or unverified guesses presented as facts.
  - Corrections replace stale entries (delete row and file, add new). One fact per entry; short.
  - New PayPal fact -> memory entry labelled V with date and call used, AND added to brief section 3 by the human.
  - Run `/memory-hygiene` weekly (days 7, 14, 21, 28) and before freeze. Target <= 25 entries (I) so index stays cheap to load.
  - Agents load only tag-matching entries; the pack tells them which tags.

## 10. Failure modes of AI-built systems and countermeasures
| failure mode | symptom | countermeasure |
|---|---|---|
| Drift between services | Provider returns field consumer does not expect | Generated clients; OpenAPI diff gate; consumer contract tests; no hand-written URLs |
| Phantom APIs | Agent calls endpoint/method that does not exist | Agents only call through `libs/clients`; reviewer greps for raw `httpx` URLs; unknown route = CI failure in compose smoke |
| Hallucinated PayPal fields/statuses/errors | Code uses field not in brief section 3 | See PayPal trace rule below |
| Silent scope growth | New endpoints, services, tables | "Not in spec = not in code" rule; CONTRACT_CHANGE_REQUEST only |
| Fake tests | Tests mock the thing under test; assert True | Reviewer checks each test can fail; mutation spot-check on mandate evaluate and refund checks (break the rule, test must fail) |
| Happy-path only | Failure-mode table rows untested | Each row in overview section 5 -> one named test per owning service |
| Float / rounding money | `float` amounts | Lint rule banning float in money packages; reviewer checklist |
| Retry on money call | Blind re-POST of refund/capture | Test: simulated timeout and 409 -> UNKNOWN, same Request-Id, no second call |
| Security regressions | Hardcoded secrets, open CORS, missing authz | Security Auditor scan on listed services; gitleaks pre-commit + CI |
| Prompt injection to money | LLM output reaches money services | AI services have no money route (credential and network boundary); output enums only; triage-ai makes no outbound calls |
| Overclaiming | README/UI says "PayPal-backed", "compliant", "tamper-proof" | Banned-phrases grep in CI over `services/web`, README, docs/demo (list from brief section 5) |
| Context rot | Late-session agent forgets rules | One slice per session; pack + memory re-read; handoff at slice end |
| Stale mocks | Stub differs from real service | Stubs generated from the same spec; stub retired once real service is on `integration` |
| "Works on my worktree" | Passes alone, fails together | Daily compose integration + golden-path script |
| Secrets leak in agent transcripts | Agent prints `.env` | Prompt forbids it; `.claudeignore`/deny rules for `.env*` (I: configure via update-config skill, day 1) |

PayPal trace rule (hard):
- Every PayPal request/response field, status, error code, and endpoint in code must map to a line in brief section 3 (verified), or carry `# UNVERIFIED-PAYPAL: <what>` and a ticket in `docs/live-checks.md`.
- paypal-adapter has a fixtures folder of REAL sandbox responses captured during the spike (secrets and personal data stripped). Unit tests parse those fixtures, not invented JSON.
- Reviewer greps for PayPal field names and confirms each against the fixtures or brief; unknown = BLOCK.
- Live-sandbox checks list (initial, from brief "NOT yet tested", all I): real return URL into our server; refund returning PENDING; webhook as hint; Disputes API (optional); buyer-side balance change; MCP from backend (we use REST, so skip). Run each once by hand or script, record result in memory as V, update brief.
- Golden-path script on the sandbox runs at least daily from day 10; any new 4xx/5xx shape is captured as a fixture.
- Gated features (Fastlane, Vault v3, Agent Ready, Store Sync, WebMCP, production Payouts) are banned: grep gate.

## 11. Daily checklists
### Morning plan (15 min)
- [ ] Read newest handoff + `git log integration --since=yesterday` + red CI list.
- [ ] Check yesterday's evening demo-readiness result; any red item is slice #1 today.
- [ ] Pick today's slices (max 3-4 concurrent agents); confirm each has a pack and spec ready.
- [ ] Confirm blockers: pending change requests, open live-checks, contract changes to apply first.
- [ ] Day-of-schedule check vs phase table; if behind, decide cut NOW (section 13).
- [ ] Launch agents with the template, one worktree each; set a review slot for each money-path PR.
- [ ] Spend check: no cards added, LLM/free-tier quotas fine, Render hours (if hosted) (deployment doc section 8).

### Midday
- [ ] Review PRs ready; send reviewer agents on finished slices.
- [ ] Apply approved contract changes; tell affected worktrees to rebase.

### Evening demo-readiness run (30-45 min)
- [ ] Merge green `svc/*` into `integration`; CI green.
- [ ] `docker compose up` fresh (volumes cleared); all `/readyz` green.
- [ ] Golden-path script (or manual click-through): sign mandate -> cart (agent or manual) -> hard-block example -> PayPal sandbox approve click -> capture -> add tracking -> advance clock -> late detected -> case -> offer -> accept -> refund COMPLETED -> audit verify OK.
- [ ] Failure drills (rotate one per night): kill mandate (expect block), LLM key invalid (expect manual cart/HUMAN_REVIEW), refund 409 simulation (expect UNKNOWN then reconcile), revoke then capture (expect CANCELLED_REVOKED).
- [ ] From day 15: same run against hosted Profile B after `scripts/warmup`; note cold-start time.
- [ ] Banned-phrase and gitleaks scans clean.
- [ ] Record timing of the 3-minute path (target total < 3:00 incl. ~25% agent segment).
- [ ] Write `/handoff`; update metrics sheet; update memory with new durable learnings.
- [ ] If anything red: log it as tomorrow's slice #1; do not start new features.

## 12. Metrics (one small table in `docs/metrics.md`, updated nightly by the human or an agent)
Velocity:
- Slices merged/day per service and cumulative vs plan (the burn-up toward the day-14 cut line).
- Spec coverage: routes implemented / routes in spec (per service).
- PR cycle time (open -> merged), and number of review rounds.
- Human review hours/day (leading indicator for the bottleneck).
Quality:
- Contract tests: pass rate; days with red `integration` (target 0 overnight).
- Spec drift incidents/week (OpenAPI diff failures) and change requests.
- Reviewer findings per PR by severity; escaped defects (found after merge).
- Golden-path success rate over last N nightly runs (target: 3 consecutive green before day 14 sign-off, I).
- Money-path invariant tests: count and mutation-check pass.
- UNVERIFIED-PAYPAL markers open (target 0 on golden path by day 14, 0 total by day 21).
- LLM cart valid-rate (target >= 95% on 20-prompt test, brief) and triage fail-closed rate.
- Cold-start time on hosted demo and end-to-end demo time.
- Banned-phrase and gitleaks hits (target 0).
Do not track lines of code or number of agent runs; they measure volume, which is not the constraint.

## 13. When to stop adding features
- Scope tiers:
  - MUST (hero, day-14 cut line): mandate sign/revoke/evaluate; seeded catalog + server pricing; checkout with real PayPal approve + capture; simulated tracking + demo clock; late detection -> case -> deterministic policy -> offer -> refund with Request-Id/reconcile; hash-chained audit + verify; gateway auth; minimal web for these screens; labels (SIMULATED CARRIER, sandbox).
  - SHOULD (days 15-21): shopping-agent propose (+ manual cart fallback), intent-fit, triage-ai classify/draft/brief, approval links for outside-terms, merchant override, Profile B hosting, warm-up.
  - COULD (only if ahead, before day 24): own MCP server tool surface demo polish, extra policy rules, reviewer brief UI, extra drills.
  - WON'T: anything on the gated list, email, real carrier data, per-merchant accounts, new services.
- Day-14 cut line (2026-10-23): Reality Checker + human test the MUST golden path on sandbox. Pass: SHOULD work proceeds. Fail: stop all new SHOULD work; the next days fix MUST; drop SHOULD items in this order of least damage: merchant override, approval-link variants, brief UI, intent-fit, triage drafts, shopping-agent (keep manual cart; the Agentic Commerce prize fit weakens, accept it), and tell the user.
- Rule: no new feature starts unless the previous night's golden-path run was green AND the feature is in the tiers above. A bug beats a feature every time.
- Day 21: hosted Profile B must be green; otherwise stop SHOULD work and fix hosting.
- Day-28 freeze (2026-11-06): no new endpoints, no schema/migration changes, no contract changes, no dependency upgrades. Allowed: bug fixes with a failing test, copy/label fixes, docs, video, README, security fixes. Each freeze-period change needs human review and a re-run of the full evening run.
- Days 29-32: only recording, submission text, repo public checks (LICENSE, `.env.example`, gitleaks clean), limits re-check (reminder 2026-11-01, deployment doc section 8), and warm-up before judges' windows. Submit 2026-11-10; the 2 days after are buffer, not build time.
- Any idea during build goes to `docs/parking-lot.md`, not to an agent prompt.

## 14. Open items
- Decide Vercel/Render/Neon final hosting after re-verifying limits (ADR-005, I).
- Confirm revoke semantics for captured orders (overview F5, I).
- Confirm that ~4-6 h/day human review is realistic (I); if not, cut MUST scope earlier, not review depth on money-path code.
- Re-read official Devpost rules for dates and sponsor prize choice (brief, VC).
