# catalog - Sprint Tasks

Labels: V verified, VC vendor claim, I inference/design assumption. Derived from `sprint-plan.md` (PRD root) for the `catalog` slice only; do not treat this as a replacement for the full sprint plan - other services' rows are not repeated here. Calendar: Day 1 = Sat Oct 10 2026. DAY-14 CUT LINE = Thu Oct 23 (end of Sprint 2). FEATURE FREEZE = Fri Nov 6, Day 28 (end of Sprint 4). Code freeze Nov 9; submit Nov 10. Each feature task is paired with a test task and a deploy task, per the standing rule in `sprint-plan.md` section 0 ("a feature is not done until its test is in CI and it is running on the hosted Profile B environment").

## Week 1 - Sprint 1, Oct 10-16 (Days 1-7)

Corresponds to `sprint-plan.md` row S1-06. This is catalog's primary build week; everything else below depends on this landing first (checkout cannot re-price without it - `sprint-plan.md` critical path section 8).

| ID | Feature task | Test task | Deploy task |
|---|---|---|---|
| CT-W1-01 | Schema + migration `0001_catalog_schema`: `catalog_versions`, `merchants`, `merchant_settlement_map`, `categories`, `items`, `item_prices`, `merchant_refund_policy_seeds`, `item_fixtures` tables; `v_items_public`/`v_prices_public`/`v_merchants_public` views; roles `catalog_ro` (SELECT-only on views), `catalog_seed` (write) | test-plan.md IT2, IT3 (grant-level enforcement) | Alembic migration applied to Neon `catalog` schema; role grants verified on the hosted DB (ADR-004 open item) |
| CT-W1-02 | Seed file `catalog_seed.json` + `0002_seed_v1` migration: 12 items / 3 virtual merchants / 6 categories, integer minor units, incl. `PW-001` injected description and `PW-004` target (spec.md #2, #7) | test-plan.md IT1 (golden price table), F1 (fixture integrity) | Seed migration run on Neon at deploy; `GET /catalog/version` confirms `item_count:12, merchant_count:3` on hosted env |
| CT-W1-03 | Idempotent startup seed (`CATALOG_SEED_ON_START`, advisory lock, hash compare) | test-plan.md IT4, IT5 (idempotent + concurrent cold start) | Safe under Render cold start / concurrent container boot; confirmed in Profile B `core` process |
| CT-W1-04 | `GET /items`, `GET /items/{sku}`, `GET /merchants`, `GET /categories`, `GET /catalog/version` (read-only, `text_trust` + `X-Data-Label` on every item) | test-plan.md CT3, U-level schema tests | Deployed in `core`; item text flagged "untrusted" in the committed contract (sprint-plan.md S1-06 test note) |
| CT-W1-05 | `POST /prices/resolve` core algorithm: strict validation (`extra=forbid`), unknown-SKU/qty/currency/duplicate/empty-cart rejection, integer-only totals, `agent_stated_price_minor` comparison flag | test-plan.md U1-U8, PI1-PI6 (price-integrity, P0) | Deployed in `core`; smoke test resolves a known cart on the hosted URL |
| CT-W1-06 | Internal JWT verification (`aud=catalog`) + per-endpoint caller allowlist, deny-by-default | test-plan.md IT8, IT9 | Wired against gateway JWKS (libs/common, S1-03 dependency) |
| CT-W1-07 | OpenAPI 3.1 contract `contracts/openapi/catalog.yaml` for the five routes above | test-plan.md CT1, CT2 | CI contract-diff gate added to the catalog path filter |
| CT-W1-08 | `/healthz`, `/health`, `/readyz` (DB + seed + version check) | test-plan.md CT5 | Health gate wired into the deploy ritual (`curl --retry` per deployment.md) |

Week 1 exit (catalog slice of sprint-plan.md S1 exit criteria): golden price table green, OpenAPI committed, Neon roles verified, hosted `/readyz` passes 3x, no float anywhere.

## Week 2 - Sprint 2, Oct 17-23 (Days 8-14) - ends at DAY-14 CUT LINE

Catalog is a read dependency for the cut-line path (sign -> cart -> real PayPal order -> approve -> return -> capture -> receipt) but is not itself re-built this week; catalog's own work supports checkout's S2-01 (re-check/re-price on capture) and the demo-reset flow (S2-09).

| ID | Feature task | Test task | Deploy task |
|---|---|---|---|
| CT-W2-01 | Version pinning on resolve (`catalog_version` param; `latest_unit_price_minor` surfaced when pinned < latest) - needed by checkout's confirm-time re-resolve | test-plan.md U10, U11, PI8 | Deployed; checkout's S2-01 integration test exercises this against the hosted catalog |
| CT-W2-02 | `POST /admin/seed`, `POST /admin/reset` (role `operator` + `PS_CATALOG_ADMIN_ENABLED` flag, append-only, never deletes history) | test-plan.md IT6, IT7 | Wired into `scripts/demo-reset` (S2-09 dependency); flag off by default in hosted env, on only for scheduled reset window |
| CT-W2-03 | `GET /admin/fixtures` (operator-only; never reachable by buyer/anonymous) | test-plan.md F4, F5 | Deployed behind the same admin flag; confirmed unreachable on a buyer-role token in the hosted IDOR pass |
| CT-W2-04 | Fixture-leak guard: confirm `item_fixtures` never joins into any public view/route (hardening pass on W1-04) | test-plan.md F2, F3, F6 | No deploy change expected; regression test added to CI so a future PR cannot reintroduce the leak |
| CT-W2-05 | IDOR / unauth enumeration pass on all catalog routes (buyer vs merchant vs operator vs anonymous) | test-plan.md IT8, IT9 - feeds the cross-service **T19** IDOR suite in `test-strategy.md` #8 S2 gate | Included in the S2 IDOR suite run against hosted Profile B |

Week 2 exit / DAY-14 CUT LINE dependency: catalog must support 5 consecutive clean hosted cut-line runs (one after >=12h idle, per `sprint-plan.md` S2 cut-line criterion 1) without re-pricing errors; version pinning and admin reset must be stable since demo reset runs between rehearsals.

## Week 3 - Sprint 3, Oct 24-30 (Days 15-21)

Catalog becomes a read dependency for `resolution`'s policy engine (refund-policy-seed) and is exercised by the injection-scene e2e test. No new P0 catalog endpoints planned this week - only hardening and the two P1/P2 items that resolution/shopping-agent may need.

| ID | Feature task | Test task | Deploy task |
|---|---|---|---|
| CT-W3-01 | `GET /merchants/{id}/refund-policy-seed` (illustrative, `authoritative:false`) for resolution's policy engine to read (REQ-CT-012, P1) | test-plan.md contract test for this route (extend CT1-CT4); resolution's own policy tests consume it | Deployed; resolution's S3 policy-engine integration test calls it against hosted catalog |
| CT-W3-02 | E2E support: confirm `PW-001`/`PW-004` fixture data flows unmodified through catalog into the shopping-agent injection scene (shopping-agent/checkout own the defense; catalog's slice is "serve verbatim, flag untrusted, never leak the marker") | test-plan.md F1-F7; cross-reference `test-strategy.md` **E3** (L5 e2e injection scene) and **T7** | No catalog deploy change; joint rehearsal with shopping-agent/checkout on hosted Profile B |
| CT-W3-03 (P2, cut candidate) | Free-text filter `q` + cursor pagination on `/items` (REQ-CT-017) | contract + unit tests for filter/pagination edge cases | Deploy only if time allows; feature-flaggable |
| CT-W3-04 (P2, cut candidate) | Outbox events `catalog.seeded` / `catalog.reset` for audit (REQ-CT-018, spec.md C3 open) | event schema test, audit consumer dedupe test | Deploy only if accepted by the audit owner; otherwise admin actions remain log-only |
| CT-W3-05 | Harden chaos slice: catalog's own behavior under **C15** (catalog down -> `/readyz` 503, no guessed price) and **C12** (Postgres cold-start window) | test-plan.md IT12, IT13 | Included in the S3 chaos pass (C1-C7, C13, C19, C20 per `test-strategy.md` #8 S3 gate - C15/C12 are catalog-adjacent additions) |

Week 3 exit: catalog supports the full hero-loop rehearsal (sign -> agent cart -> pay -> late -> triage -> policy -> refund) without being a blocker; refund-policy-seed read path stable for resolution.

## Week 4 - Sprint 4, Oct 31-Nov 6 (Days 22-28) - ends at FEATURE FREEZE

No new endpoints after Nov 6 (freeze rule in `sprint-plan.md` section 5: "no new features, no new endpoints, no schema changes"). This week is hardening, soak, and documentation only for catalog.

| ID | Feature task | Test task | Deploy task |
|---|---|---|---|
| CT-W4-01 | Full **T22** coverage pass (server derives money fields - confirm no caller-supplied price/amount/merchant ever reaches a response across every route, including edge cases found in W1-W3) | test-plan.md PI1-PI8 re-run as a full regression, not just diff-based | No code change expected if W1-W3 held; this is verification, not new feature work |
| CT-W4-02 | **T13** secrets hygiene re-pass (gitleaks full-history, log/ledger grep for `catalog_seed`/`catalog_ro` DSNs) | test-plan.md IT14 | Re-run as part of the S4 full P0 security suite (`test-strategy.md` #8 S4 gate) |
| CT-W4-03 | Reliability soak participation: catalog included in S4-05's 10 consecutive full hosted runs after 24h idle (no manual fixes allowed) | soak script asserts catalog's `/readyz` and resolve latency stay within the Profile B cold-start budget | Nightly warm-up + scheduled smoke every 6h (per `sprint-plan.md` S4-05 deploy column) |
| CT-W4-04 | Docs pass: confirm `prd.md`/`spec.md`/`api.md`/`deployment.md`/this test-plan/this sprint-tasks file all match the frozen implementation; close or explicitly re-state any open item from spec.md #12 that this sprint touched | n/a (doc review, human) | README/docs deployed alongside the freeze tag |
| CT-W4-05 | Freeze verification: confirm no catalog schema/endpoint changed after Nov 6; any post-freeze catalog change is sev-1/sev-2 bug fix only | regression suite re-run on frozen commit | Tagged with `v1.0-submission` alongside the rest of the monorepo (Nov 9 code freeze) |

## What to cut first (catalog-specific, ordered - cut from the TOP first)

Aligned with the project-wide cut list in `sprint-plan.md` section 7; this is catalog's own slice of it, ordered by what least damages the "never cut" money-path (price authority must survive intact):

| Order | Cut item | Saves | Fallback |
|---|---|---|---|
| 1 | CT-W3-04 outbox events `catalog.seeded`/`catalog.reset` (REQ-CT-018, P2) | ~0.5 day | Admin actions stay log-only; audit has no catalog-originated event, which is acceptable since catalog is not a money-event producer (service-map: "Events: none") |
| 2 | CT-W3-03 free-text filter `q` + pagination (REQ-CT-017, P2) | ~0.5 day | `/items` returns full list; UI paginates/filters client-side on the small seeded set (12 items) |
| 3 | CT-W3-01 `/merchants/{id}/refund-policy-seed` (REQ-CT-012, P1) | ~0.5 day | Resolution's 3 hardcoded policies become the sole source (consistent with the global cut-list item 8 "policy rules reduced... stated as such"); catalog's seed table stays in the DB unused but documented as reference-only |
| 4 | CT-W2-03/CT-W3-02 polish beyond the minimum fixture contract (e.g. extra fixture metadata, richer `expected_behavior` text) | ~0.25 day | `PW-001`/`PW-004` fixture itself is NEVER cut (it is the injection-scene demo item and a P0 requirement, REQ-CT-008) - only cosmetic extras around it are cuttable |

Never cut (binding, same class as the project-wide never-cut list): seeded catalog itself (12 items/3 merchants); `POST /prices/resolve` price authority and the `price_mismatch` flag (REQ-CT-002, REQ-CT-003); rejection of unknown SKU/bad qty/empty cart/currency mismatch (REQ-CT-004); `catalog_version` on every response (REQ-CT-005); read-only DB role enforcement (REQ-CT-006); `text_trust: "untrusted"` labeling (REQ-CT-007); the `PW-001`/`PW-004` injection fixture, kept operator-only (REQ-CT-008); internal JWT + caller allowlist (REQ-CT-013); `/healthz`/`/readyz` (REQ-CT-014); the committed OpenAPI contract (REQ-CT-015).

## Conflicts noted, not resolved here

Per the task's instruction to follow `service-map.md`/`adr.md` on conflicts and not rewrite other files: this sprint-tasks doc assumes the monorepo decision (ADR-009, one public repo, `services/<slug>/` folders) throughout - if any earlier catalog doc implied a separate repo, that is a conflict with the now-locked monorepo decision and should be flagged to whoever owns `prd.md`/`spec.md`, not silently fixed here. No such assumption was found in catalog's `prd.md`/`spec.md`/`api.md`/`deployment.md` on this read; they are already monorepo-consistent (deployment.md references `services/catalog/` as a path within one codebase, and Profile B co-location in `hosts/core.py`).
