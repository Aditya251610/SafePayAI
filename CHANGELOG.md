# Changelog

Generated from conventional commits (`feat:`/`fix:`/`docs:`/`chore:`/`ci:`) via
[git-cliff](https://git-cliff.org). Regenerate with:

```bash
git-cliff --output CHANGELOG.md
```

Do not hand-edit the sections below — they will be overwritten on the next regeneration.
<!-- git-cliff: end of header -->
## [unreleased]

### Features

- Scaffold monorepo workspace and 11 service skeletons
- Implement real business logic for mandate, catalog, api-gateway, and audit (Wave 5A)
- Implement paypal-adapter Wave 5B (token cache, orders, captures, ledger)
- Implement checkout order flow and shopping-agent eval harness (Wave 5B)
- Implement tracking shipment detector and resolution refund policy engine (Wave 5B)
- Wire shopping-agent live LLM calls for propose and intent-fit
- Implement triage-ai classify/draft/brief (Wave 5C)
- Implement checkout capture, receipt, and revoke-at-capture check
- Implement paypal-adapter refund_capture, get_refund, reconcile, and MCP tools
- Implement outbox relay to audit across all producer services
- Wire the fully-automated DETECTOR-origin case-to-refund loop end to end (#81)

### Bug Fixes

- Resolve uv workspace source and gitleaks CI failures (#48)
- Export per-service DATABASE_URL env vars in ci-python-service
- Resolve Docker build context, mypy config, and real type-safety bugs in Wave 5A
- Ci-gate silently passed regardless of real job failures
- Declare cryptography as an explicit mandate test dependency and fix migration bootstrap
- Declare @eslint/eslintrc as an explicit web dependency
- Audit/integration failing in CI - missing safepayai database
- Mount paypal-adapter's outbox-flush router
- Wire real auth and contract fixes found during first end-to-end hero-loop run (#80)

### Documentation

- Add PRD and architecture docs
- Rewrite README without links into the untracked .claude/ dir
- Update audit README to reflect Wave 5 status

### Miscellaneous Tasks

- Add gitignore, license, env example
- Add gitleaks, pre-commit, CODEOWNERS, PR template, and workflows
- Remove .claude internal docs/config from the public repo
- Reduce CI/Dependabot noise and add CHANGELOG.md
- Auto-generate CHANGELOG.md via git-cliff
- Regenerate changelog [skip ci]
- Regenerate changelog [skip ci]
- Regenerate changelog [skip ci]
- Regenerate changelog [skip ci]
- Regenerate changelog [skip ci]
- Regenerate changelog [skip ci]
- Regenerate changelog [skip ci]
- Regenerate changelog [skip ci]
- Regenerate changelog [skip ci]
- Regenerate changelog [skip ci]
- Regenerate changelog [skip ci]
