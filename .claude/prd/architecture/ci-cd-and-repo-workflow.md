# CI/CD and repo workflow (public monorepo, mostly AI-agent authored)

Labels: V verified, VC vendor claim, I inference/unverified. Written 2026-10-10.
Inputs: 00-context-brief.md, architecture/adr.md (ADR-009 layout), architecture/overview.md, service-map.md, deployment-zero-cost.md — all final as of 2026-10-10. Service slugs and host profiles below follow those docs directly.
Free-tier limits (Actions minutes, Render sleep, Neon limits, Vercel hobby terms) NOT re-verified here: I. Check before relying on them. Vercel Hobby is non-commercial-use (VC, recall): hackathon demo is fine, re-check.

## 1. Branching
- Trunk-based. `main` is always green and deployable. Branches live < 1 day where possible, < 3 days max.
- Names: `feat/<slug>-<what>`, `fix/...`, `chore/...`, `docs/...`, `test/...`, `ci/...`.
- Merge: squash-merge via PR only (linear history; PR title = conventional commit). No direct pushes to main (branch protection / ruleset, applies to admins too).
- Never force-push `main`. On own feature branch use `--force-with-lease` only.
- Parallel AI agents: one git worktree per agent per branch:
  `git fetch origin && git worktree add --no-track -b feat/agent-cart ../ps-agent-cart origin/main && cd ../ps-agent-cart && git push -u origin feat/agent-cart`
  Rules: one agent = one service dir where possible (path ownership avoids conflicts); shared files (`contracts/`, `libs/`, `docker-compose.yml`, workflows) are touched only by a dedicated PR that merges first, then others rebase. Clean up: `git worktree remove ../ps-agent-cart && git branch -d feat/agent-cart`.
- Rebase on `origin/main` before opening/merging (`git fetch && git rebase origin/main`).

## 2. Commits
- Conventional: `type(scope): subject` (<= 72 chars, imperative). Types: feat fix chore docs refactor test ci build perf. Scope = service slug or `contracts|libs|deploy|web`.
- Atomic: one concern per commit; migration + code that needs it in same PR, migration first and backward compatible (expand/contract).
- Enforce: `commitlint` (or `cz` check) in the PR-title job; pre-commit `commit-msg` hook optional.
- AI-agent commits carry a `Co-Authored-By:` trailer (honest provenance). Never put secrets, tokens, real emails, or PayPal IDs in messages.

## 3. PR template (.github/pull_request_template.md)
```
## What / why
## Services touched
## Tests run (paste commands + result)
## Security and honesty checklist
- [ ] No secrets/tokens/.env content in diff, logs, fixtures, screenshots (gitleaks green)
- [ ] Amounts, merchant, currency, capture_id derived server-side; no client/LLM-supplied money values
- [ ] LLM output validated against schema; failure path is fail-closed (HUMAN_REVIEW/restrictive default)
- [ ] Untrusted text (buyer free text, catalog, carrier notes) never interpolated into prompts as instructions, URLs, or SQL
- [ ] No forbidden claims (PayPal-backed/verified, legally binding, compliant, fraud-proof, injection-proof, real carrier/real money)
- [ ] Simulated parts labelled on screen (SIMULATED CARRIER, sandbox, seeded catalog)
- [ ] No PayPal logos/trademarks added
- [ ] Contract changes: openapi/events updated, generated clients regenerated, consumers checked
- [ ] Migration is backward compatible and reversible, or rollback noted
- [ ] New dependency: pinned, license checked, audit clean
- [ ] Docs/README updated if behaviour or run steps changed
```

## 4. CODEOWNERS-lite
Single human owner, goal is forced review of risky paths, not bureaucracy. `.github/CODEOWNERS`:
```
*                      @<owner>
/.github/              @<owner>
/contracts/            @<owner>
/libs/                 @<owner>
/services/*/migrations/ @<owner>
/deploy/               @<owner>
/.gitleaks.toml        @<owner>
/LICENSE               @<owner>
```
Ruleset: require PR, require CODEOWNER review on those paths (owner self-approval allowed because solo: I; GitHub blocks self-approval of own PRs, so set required approvals = 0 and rely on required status checks + the checklist), require status checks, require linear history, block force-push and deletion.

## 5. CI (GitHub Actions)
Files: `.github/workflows/ci-<slug>.yml` per service + `ci-web.yml`, `ci-contracts.yml`, `secrets.yml`, `deps.yml`. Each uses `paths:` filters on `services/<slug>/**`, `libs/**`, `contracts/**`, `pyproject.toml`/`uv.lock`, and its own workflow file. `libs/` or `contracts/` changes fan out to all services (use a reusable workflow `ci-python-service.yml` with `workflow_call` input `slug`).
Path-filter pitfall: a required check that is skipped by `paths:` stays "pending" and blocks merge. Use a single always-run `ci-gate` job (uses `dorny/paths-filter` inside, then `needs:` all conditional jobs; `if: always()` and fails only on failure/cancelled) as the ONLY required check.

Per Python service jobs (uv, Python pinned in `.python-version`):
| Job | Command (I: tool choice) |
|---|---|
| lint | `uv run ruff check . && ruff format --check .` |
| type | `uv run mypy app` (or pyright) strict on app/ |
| unit | `uv run pytest tests/unit -q --cov` (no network; PayPal and LLM mocked) |
| contract | validate FastAPI-generated OpenAPI == committed `contracts/openapi/<slug>.json` (drift fails); schemathesis/pact-style consumer check against events schemas |
| integration | job `services:` postgres (same major as Neon) + redis if used; run migrations from scratch, then `pytest tests/integration`; includes audit-log triggers block UPDATE/DELETE test, INSERT/SELECT-only role test |
| build | `docker build services/<slug>` (buildx cache); no push on PRs; on main push to GHCR (public, free: VC) tagged `sha-<short>` |
Web (`services/web`): `pnpm install --frozen-lockfile`, `eslint`, `tsc --noEmit`, `vitest`, `next build`, optional Playwright smoke against compose stack.
Repo-wide: `docker compose config`, yaml/markdown lint, link check on README (non-blocking).
Tests never call live PayPal or LLMs in CI. Sandbox PayPal checks live in a separate manual `workflow_dispatch` job in the `sandbox` environment (secrets scoped there). Fork PRs get no secrets (default); keep it that way, never use `pull_request_target` with checkout of PR code.
Hardening: `permissions: contents: read` default; pin third-party actions by commit SHA (Dependabot updates them); `concurrency` cancel-in-progress per ref; timeouts on every job.

## 6. Secret scanning (3 layers)
1. pre-commit (`.pre-commit-config.yaml`): `gitleaks protect --staged`, plus ruff, end-of-file, large-file check. Agents must run `pre-commit install` in every worktree (hooks are per-clone; worktrees share `.git/hooks` so one install is enough: V, git behaviour) and CI is the real gate.
2. CI `secrets.yml`: `gitleaks detect --log-opts="--all"` full history on every PR and weekly cron; fail blocks merge. `.gitleaks.toml` extends default rules, adds custom rule for PayPal client secret-like strings (assumption I: pattern from key shape, do not paste real value), allowlist only `.env.example` placeholders and test fixtures marked `fake`.
3. GitHub: enable Secret scanning + Push protection (free on public repos: V per GitHub docs, recall; confirm in Settings) and private vulnerability reporting.
If a secret leaks: rotate at PayPal first (history rewrite does not un-leak), then purge, then note in a private log.

## 7. Dependencies and SBOM-lite
- Python: `uv.lock` committed; CI uses `uv sync --frozen`. Node: `pnpm-lock.yaml` + `--frozen-lockfile`. Docker base images pinned by digest (Dependabot docker ecosystem bumps them). Actions pinned by SHA.
- Audit in `deps.yml` (PR + weekly): `uv export --no-hashes | pip-audit -r /dev/stdin` (or `uvx pip-audit`), `pnpm audit --prod`; high/critical fails PR, others warn. Dependabot for pip/npm/docker/actions, weekly, grouped.
- License check: `pip-licenses` / `license-checker` fail on GPL/AGPL if repo license is permissive (I: decide license first).
- SBOM-lite: on release tag, generate CycloneDX (`cyclonedx-py` for each service, `@cyclonedx/cyclonedx-npm` for web) and attach to the GitHub Release. No signing claims.
- Rule: new dependency needs a one-line justification in PR; prefer stdlib; no packages younger than ~1 week or with typosquat-like names (agents hallucinate package names: verify on registry).

## 8. Deploy pipelines (zero-cost targets; targets per brief: Vercel web, Render API, Neon DB)
- Trigger: push to `main` after CI green (`workflow_run` or same workflow `needs`). GitHub Environments: `preview`, `staging` (optional), `production`, `sandbox`. `production` requires a manual approval step and restricts to `main` branch.
- Order: (1) migrate Neon, (2) deploy API/services, (3) deploy web, (4) warm-up + smoke. Migrations are expand/contract so old code runs on new schema.
- Neon: `uv run alembic upgrade head` (I: migration tool) from a CI job using `NEON_DATABASE_URL` env-scoped secret; PR previews use a Neon branch per PR (`neonctl branches create --name pr-<n>`, deleted on PR close; Neon branching is a free-plan feature: VC, verify limits). Migration role differs from runtime role; runtime role for audit table is INSERT/SELECT only.
- Render (Profile B hosts `edge|core|ai|paypal`, I): connect repo with `deploy/profile-b/render.yaml`; autodeploy OFF, deploy via Deploy Hook / API from the pipeline so migrations go first. Free web services sleep after idle (VC; verify) so warm-up is mandatory. PR previews: Render preview environments may need paid plan (I) so previews = Vercel web preview pointing at the shared staging API with sandbox creds.
- Vercel: Git integration gives a preview per PR (V, standard behaviour); production on `main`. Env vars set in Vercel dashboard, only public ones prefixed `NEXT_PUBLIC_`; no secret in client bundle (CI grep check of `.next` for known key prefixes).
- Smoke + warm-up (`scripts/warmup`): after deploy, loop with retries (up to ~90 s, I) on each service `/healthz` and `/readyz` (DB reachable, migrations at expected head), then scripted smoke: seed check, GET catalog, create mandate, hit `verify chain` endpoint, one PayPal sandbox OAuth token call via adapter health (no order). Fail = pipeline red and auto-rollback step. Run warm-up again ~10 min and 30 min before any demo/recording; optional cron ping workflow (respect Actions limits and ToS; I).
- Rollback: Render: redeploy previous image/commit via API (keep last 3 SHA tags in GHCR); Vercel: `vercel rollback` / promote previous deployment; Neon: no destructive down-migrations in production, fix-forward or restore via Neon point-in-time/branch restore (history window on free plan: unknown, verify). Because migrations are backward compatible, app rollback needs no DB rollback. Record in `docs/runbook.md`.

## 9. Environments and secrets
- Never commit `.env`. Real values live only in: local `.env` (gitignored), GitHub Environment secrets, Render env, Vercel env, Neon console. Repository-level secrets only for CI-wide items; deploy tokens in the `production` environment.
- `.env.example` holds names + safe placeholders + comments only: PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, PAYPAL_ENV=sandbox, PAYPAL_CURRENCY=USD (current file has these 4; V). Add as built (placeholders like `changeme`/empty): DATABASE_URL (local compose default), MANDATE_HMAC_KEY, JWT/gateway signing key, SERVICE_TOKEN secrets, LLM_API_KEY, LLM_MODEL, WEB_BASE_URL, API_BASE_URL, DEMO_CLOCK_ENABLED. Never a real-looking value; CI check: every var used in code via `os.environ`/settings appears in `.env.example` (script `scripts/check_env_example.py`).
- Only shopping-agent and triage-ai get LLM keys (ADR-010); only paypal adapter gets PayPal creds. Scope Render env groups accordingly.
- Separate sandbox credentials from anything else; sandbox only, never live keys, and say so in README.

## 10. Release for submission
- Target submit 2026-11-10 (deadline 2026-11-12 noon PT, VC).
- 2026-11-03: feature freeze (only fixes). 2026-11-07: release candidate `v1.0.0-rc1`, full manual E2E on deployed stack, record video from that build.
- Release: `git tag -a v1.0.0 -m "Hackathon submission" && git push origin v1.0.0`; GitHub Release with notes, SBOM files, known limitations. Tag protection ruleset on `v*`. Freeze: `main` ruleset tightened (only `fix:` PRs w/ owner), and submit the tag URL plus the demo URL. Judges may view the repo after the deadline: do not rewrite history or delete the tag; post-deadline work goes on a `post-submission` branch.
- Gating checks on tag (`release-check.yml`, must pass before release is published): LICENSE exists and is OSI-approved (check SPDX id, e.g. MIT/Apache-2.0: pick one, I), README contains: what it is, honest limitations/"sandbox only, simulated carrier" section, architecture diagram link, run-locally steps (`cp .env.example .env`, `docker compose up`), hosted demo link, video link, test commands, license badge; link check; no `TODO`/`FIXME` in README; no forbidden-claim phrases (grep list from brief section 5); gitleaks full history clean; `docker compose up` smoke from clean checkout; `.env` not tracked (`git ls-files | grep -E '(^|/)\.env$'` empty); no PayPal logos in repo (`find` for known filenames, manual).

## 11. Definition of ready to merge
1. PR title is a conventional commit; branch rebased on `main`; squash-merge.
2. `ci-gate` green (lint, types, unit, contract, integration, build for affected services) and gitleaks green.
3. Checklist in the PR template fully ticked, no unexplained N/A.
4. Contracts/generated clients in sync; migration backward compatible; new env vars in `.env.example`.
5. New behaviour has tests, including a fail-closed/negative test for anything touching money, mandate, LLM output.
6. No new high/critical audit findings; new deps justified and pinned.
7. Docs/README/runbook updated; no forbidden claims; simulated parts labelled.
8. Preview (web) or local compose manually checked for UI changes (screenshot in PR).
9. CODEOWNERS paths reviewed by owner.

## 12. git init and first-commit hygiene (repo currently NOT a git repo; V from env)
Existing at root: `.env`, `.env.example`, `.gitignore`, `.claude/`, plus a `spike/` referenced by .gitignore (may not exist now).
Current `.gitignore` (V, read): `.env`, `.env.*`, `!.env.example`, `spike/results.json`, `spike/results2.json`, `spike/.approved`, `__pycache__/`, `.venv/`, `node_modules/`. Covers the main secret file and variants (`.env.local` etc.). GAPS to add before first commit:
```
# secrets / keys
*.pem
*.key
*.p12
*.pfx
secrets/
*.tfstate*
# spike artifacts may hold tokens/order IDs: ignore whole dir unless scrubbed
spike/
# tooling
.claude/settings.local.json
.pytest_cache/ .ruff_cache/ .mypy_cache/ .coverage htmlcov/
.next/ dist/ build/ *.egg-info/ .vercel/ .turbo/
*.log
.DS_Store
.idea/ .vscode/
```
Decision to make: whether `.claude/prd/` is committed (it is planning docs; no secrets by rule; public repo shows AI process: fine but scrub first) - default: commit `.claude/prd` after gitleaks, ignore settings.local.json and any memory/transcript files.
Exact steps (run from /home/harsh/Projects/artiq; fish shell syntax fine for these):
1. Append the gap entries to `.gitignore` (edit, do not overwrite).
2. `git init -b main`
3. `git config user.name` / `user.email` set (use a GitHub noreply email, not a personal one, since the repo is public: GitHub Settings > Emails > "Keep my email private").
4. `git check-ignore -v .env` must print the `.env` rule; `git check-ignore -v .env.example` must print nothing (it must be tracked).
5. Review `.env.example`: values must be placeholders only. Check with `sed 's/=.*/=/' .env.example` that nothing real lingers; compare against `.env` NOT by printing it (use `grep -c` of each .env value in .env.example without echoing, or just inspect that example lines are blank/placeholder).
6. Scan before staging: `gitleaks detect --no-git --source . --redact -v` (working tree, incl. `.claude/` and `spike/`) must be clean.
7. Add LICENSE (chosen OSI license), minimal README, `.gitleaks.toml`, `.pre-commit-config.yaml`, `.github/` skeleton (workflows, CODEOWNERS, PR template), then `pre-commit install`.
8. `git add -A && git status --short` and eyeball: `.env` must NOT appear; run `git ls-files | grep -E '(^|/)\.env($|\.)'` expecting only `.env.example`.
9. `gitleaks protect --staged --redact -v` clean.
10. Commit in small atomic commits: `chore: add gitignore, license, env example` ; `docs: add PRD and architecture docs`; `ci: add gitleaks and pr template`. Footer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
11. Create the GitHub repo as PRIVATE first (`gh repo create safepayai --private --source . --remote origin`), `git push -u origin main`, then enable secret scanning/push protection, rulesets, Actions settings; run full-history gitleaks in CI; flip to public only once clean. Reason: a leaked key in public history is permanent. Since the PayPal secret in `.env` was used in spikes, consider rotating the sandbox secret before going public anyway (cheap).
12. Verify after push: `git ls-remote origin`, GitHub Security tab shows push protection on.

## Open questions
- License choice (MIT vs Apache-2.0); repo name vs working name "SafePayAI".
- Profile A vs B host layout and service slugs: reconcile with service-map.md / deployment-zero-cost.md when they exist.
- Free-tier limits (Actions minutes on public repos are free: VC; Render/Neon/Vercel limits) to verify.
- Whether solo ownership allows approval rules (see section 4).
