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
- Implement resolution GET /cases and GET /review/queue (were 501 stubs) (#82)
- Complete the resolution reviewer wave + fix real paypal-adapter stub gap (#83)
- Implement checkout and shopping-agent internal outbox/reconcile/events endpoints (#87)
- Wire real CSRF, missing gateway routes, and a frontend integration contract (#90)
- Real per-merchant tenancy and a merchant-scoped order filter (#92)
- Implement gateway's ops and bff aggregator routes (#93)
- Wire a real per-event timeline into triage-ai's consistency checks (#94)
- Wire mandate's real reservation lifecycle into checkout's capture flow (#95)
- Close the last backend gaps - real bff aggregators, triage item_titles, mandate sweep cron (#96)

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
- Mandate revocation + capture identity bugs, sync all docs to real tested state (#84)
- Wire real HMAC authorization-ticket verification + fix mandate-block crash + fix a real refund-race crash (#86)
- Close 5 backend security/correctness gaps found in a hackathon code review (#88)
- Agent/catalog mismatch, cap race, and resolution/refund hardening (#89)
- Close Profile B's app-package import collision in hosts/_mount.py (#97)
- Correct render.yaml blueprint schema and build command (#98)
- Guard catalog's dev-password migration step for production (#99)
- Grant audit_owner membership before transferring schema ownership (#100)

### Documentation

- Add PRD and architecture docs
- Rewrite README without links into the untracked .claude/ dir
- Update audit README to reflect Wave 5 status
- Record live webhook signature verification (#85)

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
- Fail-fast on placeholder secrets and harden docker/compose (#91)
- Regenerate changelog [skip ci]
- Regenerate changelog [skip ci]
- Regenerate changelog [skip ci]
- Regenerate changelog [skip ci]
- Regenerate changelog [skip ci]
- Regenerate changelog [skip ci]
- Regenerate changelog [skip ci]
- Regenerate changelog [skip ci]
- Regenerate changelog [skip ci]
