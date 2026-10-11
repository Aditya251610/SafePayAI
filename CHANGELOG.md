# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). This project does not
use semantic version tags during the hackathon build — entries are grouped by build wave instead
(see the project's sprint plan), with a `v1.0.0` tag planned at submission.

## [Unreleased]

### Added
- Wave 5 (in progress): real business logic replacing Wave 4's `501` stubs, backend services
  first — `mandate`, `catalog`, `api-gateway`, `audit` landing first (no cross-service
  dependencies), then `paypal-adapter`/`checkout`/`shopping-agent`/`triage-ai`, then the
  `tracking`/`resolution` refund loop. No frontend work until the backend is complete end to end.
- `CHANGELOG.md` (this file).

### Changed
- All work now lands via PRs (`feature/`, `fix/`, `chore/` branches; commit messages and PR
  titles both `feat:`/`fix:`/`chore: ...`), squash-merged. Earlier Wave 4 commits were made
  directly to `main` before this convention was adopted.
- Reduced CI/Dependabot noise: `secrets` and `deps` workflows no longer also trigger on push to
  `main` (a squash-merge re-runs an identical check the PR already ran); `deps` is now path-filtered
  to only fire when a dependency manifest actually changes; Dependabot schedule moved from weekly
  to monthly for the length of this project.

### Fixed
- `ci-gate` failing on every service: 6 of 10 services referenced the shared `safepayai-common`
  library via a `tool.uv.sources` path instead of `{ workspace = true }`, which uv rejects for an
  actual workspace member — `uv sync` failed before any lint/test/build step ran.
- `secrets` / `release-check` gitleaks step failing: `gitleaks/gitleaks-action@v2` now requires a
  paid `GITLEAKS_LICENSE` for most usage (an unrelated upstream breaking change). Both now run the
  gitleaks binary directly instead.

## Wave 4 — 2026-10-11

### Added
- Monorepo scaffolding for all 11 services (`api-gateway`, `mandate`, `catalog`,
  `shopping-agent`, `checkout`, `paypal-adapter`, `tracking`, `resolution`, `triage-ai`, `audit`,
  `web`): FastAPI skeletons with real `/health`+`/readyz`, every other route a `501` stub matching
  its OpenAPI contract, an Alembic baseline migration per service, Dockerfile, `.env.example`.
- `contracts/openapi/*.yaml` for all 10 backend services.
- `libs/common` shared infra (JWT mint/verify, `authorization_ticket` HMAC, DB grants helper,
  HTTP client defaults, LLM gateway interface — no business logic).
- `docker-compose.yml` (Profile A, full local separation) and a Profile B co-located-host design
  (`hosts/{edge,core,ai,paypal}.py`, `deploy/profile-b/render.yaml`) for the free-tier hosted demo.
- Full CI/CD: `ci-gate` (path-filtered per service, single required check), reusable
  `ci-python-service.yml`, `ci-web.yml`, `ci-contracts.yml`, `secrets.yml`, `deps.yml`,
  `release-check.yml`, `keepwarm.yml`, Dependabot, `.gitleaks.toml`, pre-commit, CODEOWNERS, PR
  template.
- MIT `LICENSE`.

### Changed
- Reconciled a cross-service naming inconsistency surfaced during Wave 4 scaffolding: `checkout`
  and `paypal-adapter` had used service-doc-specific DB role names (`checkout_app`, `paypal_app`)
  while every other service used the platform-wide `svc_<slug>`/`mig_<slug>` convention —
  standardized all 10 on the generic scheme.
- Removed `.claude/` (internal PRD, architecture docs, agent/memory configuration) from the public
  repo; it remains on disk locally but is now gitignored.
