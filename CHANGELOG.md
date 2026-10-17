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
- Real upstream checks in checkout's /readyz (#101)
- *(web)* Typed api integration layer with csrf, idempotency, error normalisation and money-route reconcile (#110)
- *(web)* Design foundation - tokens, fonts, logo, ui primitives, shell, session (#111)
- *(web)* Public pages - landing story, sign-in and error copy (#112)
- *(web)* Mandate screens - buyer home, sign a mandate, mandate detail (#113)
- *(web)* Shop and agent screens - intent form, draft proposal, cart build (#114)
- *(web)* Cart and payment return - rules view, approve, PayPal handoff, capture (#115)
- *(web)* Orders - list, order detail with receipt, report a problem (#116)
- *(web)* Resolution - case screen with offer decisions, approval link consent (#117)
- *(web)* Audit log - chain verification and paged entries for every role (#118)
- *(web)* Merchant desk and case actions, plus local fonts (#119)

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
- Keepwarm pinged the wrong route and only one of 4 Render hosts (#102)
- Gateway was missing the mandate preview proxy route entirely (#103)
- Shopping-agent's internal-JWT audience didn't match the gateway's (#104)
- Shopping-agent now mints its own outbound service tokens (#105)
- Mandate only trusted api-gateway as an internal-JWT issuer (#106)
- Give each co-mounted service a unique internal package name (#107)
- Shopping-agent read the wrong field name for mandate's merchant allowlist (#108)

### Documentation

- Add PRD and architecture docs
- Rewrite README without links into the untracked .claude/ dir
- Update audit README to reflect Wave 5 status
- Record live webhook signature verification (#85)
- Sync frontend-integration-contract with the real live deploy (#109)

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
