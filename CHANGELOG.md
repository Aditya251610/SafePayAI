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

### Bug Fixes

- Resolve uv workspace source and gitleaks CI failures (#48)
- Export per-service DATABASE_URL env vars in ci-python-service
- Resolve Docker build context, mypy config, and real type-safety bugs in Wave 5A
- Ci-gate silently passed regardless of real job failures
- Declare cryptography as an explicit mandate test dependency and fix migration bootstrap
- Declare @eslint/eslintrc as an explicit web dependency
- Audit/integration failing in CI - missing safepayai database

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
