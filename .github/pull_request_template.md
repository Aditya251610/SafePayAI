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
