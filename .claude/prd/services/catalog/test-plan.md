# catalog - Test Plan

Labels: V verified, VC vendor claim, I inference/design assumption. Scope: `services/catalog`. Source of truth: `prd.md`, `spec.md`, `api.md`, `deployment.md` (this folder); test IDs below are referenced from the PRD-root `test-strategy.md` (S/C/T series) where applicable - catalog has no dedicated S-series entries of its own (those cover PayPal spike behavior); it maps into T/C/L series as noted. No invented pass-rate numbers beyond what `prd.md` section 4 and `test-strategy.md` already state; where a target is not defined, this doc says "no target set (I)".

## 1. Unit tests (L1)

| id | case | ref |
|---|---|---|
| U1 | `unit_price_minor` and `line_total_minor` are always int; no float anywhere in request/response models or math | test-strategy.md L1 "catalog: integer minor-unit pricing... no float anywhere" |
| U2 | Property test: for any valid line set, `sum(line_total_minor) == total_minor` | test-strategy.md L1 (property test note) |
| U3 | `qty` validation: rejects 0, negative, non-integer, qty > `PS_CATALOG_MAX_LINE_QTY` -> `INVALID_QUANTITY` | spec.md #9 |
| U4 | Duplicate SKU in one request -> `DUPLICATE_SKU_LINE`, no partial pricing | spec.md #5, #9 |
| U5 | Empty `lines` -> `EMPTY_CART` | spec.md #9 |
| U6 | Unknown SKU (single and multiple) -> `UNKNOWN_SKU` with full offending list in `details.skus`, never partial success | spec.md #5 step 4, #9 |
| U7 | Currency present and != `USD` -> `CURRENCY_MISMATCH`; currency omitted -> defaults from DB | spec.md #3.4 |
| U8 | Extra/unknown body fields (anything but documented `agent_stated_price_minor`) -> 422 `VALIDATION_ERROR` (`extra=forbid`) | spec.md #3.2, #9 |
| U9 | Seed hash is deterministic SHA-256 of canonical JSON of `catalog_seed.json` | spec.md #2 |
| U10 | Inactive item (`active=false`) in latest version -> `ITEM_INACTIVE`; same SKU still prices under an older pinned version where it was active | spec.md #4 |
| U11 | Unknown `catalog_version` on resolve -> 404 `CATALOG_VERSION_UNKNOWN` | spec.md #4, #9 |
| U12 | `merchant_id`, `category_id`, `settlement_alias` on a resolved line always come from the item/merchant row, never from the request body (no such input fields exist on the schema) | spec.md #3.5 |

## 2. Price-integrity tests (P0 - the core contract of this service)

Server price is authoritative; any agent/client-stated price is informational only and a mismatch is rejected downstream. These are the tests that back REQ-CT-003 and `prd.md` metric "Price-integrity test pass rate... must be 100% (binary gate)". Maps to **T22** (server derives money fields - checkout, resolution, adapter, catalog) in test-strategy.md #11.

| id | case | expected |
|---|---|---|
| PI1 | Resolve a line with `agent_stated_price_minor` equal to DB price | `price_mismatch: false`; math uses DB price |
| PI2 | Resolve a line with `agent_stated_price_minor` lower than DB price (e.g. agent says 4000, DB has HH-002 at 4500) | `price_mismatch: true`; `line_total_minor` computed from DB price (4500), NOT the agent-stated value; `price_mismatch_any: true` at top level |
| PI3 | Resolve a line with `agent_stated_price_minor` higher than DB price | same as PI2, direction reversed; DB still wins |
| PI4 | Resolve with no `agent_stated_price_minor` at all | `price_mismatch: false`; no comparison attempted |
| PI5 | Resolve a cart where a top-level `total` / `amount` / `price` field is injected in the request body | rejected at schema level -> 422 `VALIDATION_ERROR` (`extra=forbid`); nothing resolved, no partial pricing |
| PI6 | Fuzz: 50 generated line sets with random `agent_stated_price_minor` values (incl. negative, zero, huge int) always produce a response whose `total_minor` equals the DB-only sum | 100% DB-sourced totals; stated price never leaks into the sum |
| PI7 | Downstream contract check (consumer-driven, run from checkout's test suite but asserted here too): checkout feeding a mismatched `agent_stated_price_minor` line into `/prices/resolve` gets `price_mismatch: true` back, which checkout turns into hard-block `PRICE_MISMATCH` (checkout owns the block decision; catalog owns the flag) | catalog returns the flag; checkout's own test asserts the hard-block - do not duplicate checkout's test here, only assert the flag contract |
| PI8 | Pinned-version resolve where latest price differs from the pinned price | response includes `latest_unit_price_minor` on the differing line; pinned price (not latest) is what is summed into `total_minor` for that call | spec.md #4 |

CI gate: PI1-PI6 and PI8 run on every PR touching `services/catalog/**`; 100% pass required (binary gate per `prd.md` #4), no quarantine allowed on PI1-PI3/PI5/PI6 (price-integrity is a money-path invariant, same class as test-strategy.md #9 "Mandatory... money-path invariant tests... CANNOT be quarantined").

## 3. Injected-description demo item fixture (PW-001 / PW-004)

Backs spec.md #7 and the demo injection scene (agent-and-mcp-design scene 1). Maps to test-strategy.md **E3** (injection scene, L5 e2e) and the **T7** injection-corpus line (shopping-agent, triage-ai, checkout, resolution - catalog's role is to serve the fixture unmodified, not to defend against it).

| id | case | expected |
|---|---|---|
| F1 | Seed fixture integrity: `PW-001` exists, `mrc_pixelwire`, `electronics`, `unit_price_minor = 1299`, description is non-empty and UNCHANGED from the committed seed file hash | fixture presence binary gate per `prd.md` #4 "Injection fixture presence" |
| F2 | `PW-001` description on `GET /items`, `GET /items/{sku}`, and inside `/prices/resolve` responses is returned byte-for-byte identical to the seed file (catalog does not sanitize) | verbatim serving (spec.md #7) |
| F3 | Public item JSON for `PW-001` (and all items) carries `text_trust: "untrusted"` and contains NO fixture/injection marker key, flag, or hint of any kind | REQ-CT-007, REQ-CT-008; `prd.md` risk "Fixture flag leaks to model" |
| F4 | `item_fixtures` row for `PW-001` (`kind=PROMPT_INJECTION_DESCRIPTION`, `target_sku=PW-004`) is retrievable ONLY via `GET /admin/fixtures` with role `operator` + `PS_CATALOG_ADMIN_ENABLED=true`; buyer/merchant/anonymous roles get 403/401 | spec.md #7, api.md "Never reachable by buyer or anonymous" |
| F5 | `item_fixtures` table/view is never joined into `v_items_public`, `v_prices_public`, or any public-facing query path (static query audit + integration test asserting the public views' column list excludes fixture columns) | spec.md #1 "NOT in public views" |
| F6 | `PW-004` (injection target, 24900, over any demo cap) resolves normally like any other item - it carries no special flag itself | spec.md #7 "Also seeded: PW-004 as the injection target" |
| F7 (integration, owned jointly with shopping-agent/checkout, catalog's slice only) | Feed `PW-001`'s raw description through catalog's response into a stub LLM-gateway wrapper test: confirm catalog's `text_trust` field is present and the wrapper treats it as untrusted/delimited data (does not assert agent behavior - that's shopping-agent's T7 test) | confirms the handoff contract catalog promises, not the agent's defense |

## 4. Contract tests (L2)

| id | case |
|---|---|
| CT1 | `contracts/openapi/catalog.yaml` matches implemented routes/schemas; CI fails on undeclared diff (ADR-008, REQ-CT-015) |
| CT2 | Generated client from the committed OpenAPI compiles and can call a mock server started from the same spec |
| CT3 | Every response from `/items`, `/items/{sku}`, `/prices/resolve` carries `X-Data-Label: simulated-seed` and `X-Request-Id` headers |
| CT4 | Error body shape `{"error":{"code","message","details","request_id"}}` matches spec.md #9 for every documented error code |
| CT5 | `/healthz`, `/health`, `/readyz` respond per api.md "Health" section; `/readyz` returns 503 `NOT_READY` when DB or seed is missing (simulate via test DB without seed applied) |

## 5. Integration tests (L3, ephemeral Postgres schema `catalog`)

| id | case |
|---|---|
| IT1 | Golden price table: every seeded SKU (12 items) resolves to its documented `unit_price_minor`; total item/merchant/category counts match `GET /catalog/version` (`item_count:12, merchant_count:3`) |
| IT2 | Runtime role `catalog_ro` can only SELECT on `v_items_public`, `v_prices_public`, `v_merchants_public`, `catalog_versions`, `merchant_refund_policy_seeds`; any INSERT/UPDATE/DELETE attempt with that role fails at the DB grant level (REQ-CT-006) |
| IT3 | Seed/admin role `catalog_seed` is the only role that can write; verified by attempting the same write with `catalog_ro` and expecting a DB-level permission error |
| IT4 | Seeding is idempotent: run seed twice sequentially -> `catalog_version` unchanged on the second run, `changed:false` |
| IT5 | Concurrent cold start: launch N parallel seed attempts under the advisory lock -> exactly one version inserted, no deadlock, no duplicate rows (REQ-CT-010) |
| IT6 | `POST /admin/seed` / `POST /admin/reset` return 403 `ADMIN_DISABLED` when `PS_CATALOG_ADMIN_ENABLED=false`; 200 with `actor` logged when enabled and caller has role `operator` |
| IT7 | `POST /admin/reset` never deletes rows from `item_prices` or `catalog_versions`; history row count only grows |
| IT8 | JWT enforcement: missing token -> 401 `UNAUTHENTICATED`; wrong `aud` -> 401; expired -> 401; caller not in the per-endpoint allowlist (e.g. buyer calling `/admin/seed`) -> 403 `FORBIDDEN`. Maps to test-strategy.md **T19** (every verifier) and **T13/T14** class (deny-by-default) |
| IT9 | Caller allowlist matrix per api.md #Endpoints table: checkout/shopping-agent/gateway-BFF can call `/prices/resolve`; resolution/merchant-via-gateway can call `/merchants/{id}/refund-policy-seed`; any other caller role gets 403 |
| IT10 | Mixed-merchant cart resolves correctly with per-line `merchant_id` and `settlement_alias`, and `merchant_ids` at top level lists each merchant once (spec.md #3.6) |
| IT11 | `PS_CATALOG_MAX_LINES` and `PS_CATALOG_MAX_LINE_QTY` bounds enforced; request above either bound rejected before any DB query (defense against oversize input, test-strategy.md T16 class) |
| IT12 | Chaos **C15** slice (catalog's own side): with the DB connection intentionally broken, `/readyz` returns 503 `NOT_READY` and `/prices/resolve` fails fast (no hang, no partial pricing) rather than returning a stale or guessed price - this is the contract checkout's own C15 test ("catalog down -> cannot re-price -> block") depends on |
| IT13 | Chaos **C12** slice: Postgres cold-start / connection-refused window (30-60 s) - caller retries on the idempotent `/prices/resolve` with backoff eventually succeed once catalog's DB is reachable; no half-applied seed state |
| IT14 | Secrets/log hygiene (**T13** class): `catalog_seed`-role DSN and any secret value never appear in logs, error bodies, or `/admin/*` responses; gitleaks pass on this service's files |

## 6. CI side-by-side commands

Run locally and in CI exactly as below (path-filtered on `services/catalog/**`, per `deployment.md` CI/CD section):

```bash
# lint + types
ruff check services/catalog
ruff format --check services/catalog

# unit + integration (ephemeral Postgres schema, pytest marks separate L1 vs L3)
pytest services/catalog/tests -m "unit" -q
pytest services/catalog/tests -m "integration" -q --maxfail=1

# price-integrity + fixture gates (binary, no quarantine)
pytest services/catalog/tests/test_price_integrity.py -q
pytest services/catalog/tests/test_injection_fixture.py -q

# contract: generate from committed spec, diff against implementation
python -m scripts.contract_diff --service catalog --spec contracts/openapi/catalog.yaml

# security/static
gitleaks detect --source services/catalog --no-git -v
pip-audit -r services/catalog/requirements.txt   # or uv export equivalent

# readiness gate after deploy (used by deployment.md health gate step)
curl --retry 5 --retry-delay 5 --fail https://<catalog-host-or-core>/readyz
```

CI must run unit+contract+price-integrity+fixture+security on every PR touching `services/catalog/**`; integration (ephemeral DB) and the `/readyz` deploy gate run on merge to main, per the per-sprint CI gating table in `test-strategy.md` #8 (catalog work lands under the S1/S2 gate rows: "L1 mandate/audit/gateway" expands to include catalog from S1-06 onward; T22/T19/T13 apply from the sprint they are introduced).

## 7. Definition of done

A catalog change is "done" only when ALL of the following hold (mirrors the DoD pattern in `sprint-plan.md` S1/S4, applied to this service):

1. Every new/changed endpoint has a unit test, a contract entry in `contracts/openapi/catalog.yaml`, and (if it touches pricing) a price-integrity test (section 2).
2. PI1-PI6, PI8, F1-F6 pass at 100% - no exceptions, no quarantine (price-integrity and the injection fixture are money-path/safety invariants).
3. CI is green on the commands in section 6: ruff, pytest (unit+integration), contract diff, gitleaks, pip-audit.
4. No float appears anywhere in request/response models or arithmetic (U1, U2 property test green).
5. No price, amount, total, or merchant identifier accepted from a caller ever changes a resolve response (U12, PI1-PI6).
6. `/admin/*` routes are unreachable without `PS_CATALOG_ADMIN_ENABLED=true` and role `operator` (IT6); the injection fixture is unreachable by any non-operator caller (F4).
7. Seeding is verified idempotent and safe under concurrent cold start (IT4, IT5) before merging any seed-path change.
8. `/readyz` correctly reflects DB/seed state (CT5, IT12) and the service fails closed (never serves a guessed price) when the DB is unavailable.
9. Deployed to the target Profile B process (`core`) and the hosted `/readyz` health gate passes per `deployment.md`.
10. All response/doc text carries the required honesty labels (`X-Data-Label: simulated-seed`, `text_trust: "untrusted"`) - REQ-CT-016.
11. Any open conflict this change touches (spec.md #12 C1-C11) is either resolved in this doc set or explicitly left open with its current position stated - test-plan.md and sprint-tasks.md are NOT the place to resolve those; flag only.

No invented pass-rate targets beyond `prd.md` #4 (binary gates) and the CI gating table in `test-strategy.md` #8/#10; where a numeric target does not already exist in those docs, none is set here.
