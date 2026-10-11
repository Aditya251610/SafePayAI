# catalog - PRD

Labels: V verified, VC vendor claim, I inference/design assumption. Date 2026-10-10. Everything here is SIMULATED/seeded and sandbox-only.

## 1. Role
- Single source of price truth for SafePayAI. Serves ~12 seeded items from 3 VIRTUAL merchants, all of which settle to ONE sandbox merchant account (V: brief section 2; service-map). Prices are integer minor units, USD only.
- Money-path service for prices only. It holds no PayPal credentials, no LLM, no user data, and emits no money events.
- Its text fields (title, description) are UNTRUSTED when they reach an LLM. One seeded item carries a deliberately injected description for the demo injection scene (agent-and-mcp-design demo scene 1).
- Python 3.12 + FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic (V: ADR-002). Schema `catalog` in the shared Postgres, own DB role (ADR-004).

## 2. Requirements
| id | requirement | priority |
|---|---|---|
| REQ-CT-001 | Seed exactly 12 items across 3 virtual merchants and 6 categories, all in USD, prices as positive integers in minor units (no floats anywhere). | P0 |
| REQ-CT-002 | `POST /prices/resolve` takes `[{sku, qty}]` and returns priced lines, `total_minor`, `currency`, `catalog_version`. Prices come only from the DB. | P0 |
| REQ-CT-003 | Any price, amount, or total sent by a caller is never used. If a line carries `agent_stated_price_minor` and it differs from DB, the response flags `price_mismatch: true` for that line (checkout turns it into hard-block `PRICE_MISMATCH`). | P0 |
| REQ-CT-004 | Unknown SKU, qty < 1, non-integer qty, qty over the technical bound, duplicate SKU lines, empty cart, or unknown currency are rejected with a stable error code (no partial pricing). | P0 |
| REQ-CT-005 | Every resolve response and item response carries `catalog_version`. Callers may pin a version; a pinned resolve prices from that version's append-only price rows. | P0 |
| REQ-CT-006 | `GET /items`, `GET /items/{sku}`, `GET /merchants`, `GET /categories` are read-only. The runtime DB role has SELECT only on public views. | P0 |
| REQ-CT-007 | Each item response carries `text_trust: "untrusted"` for title/description so consumers wrap it before any LLM call. | P0 |
| REQ-CT-008 | Seed one deliberately injected description (item `PW-001`). Its flag lives in a separate fixture table and is returned only to operator/test callers, never on public item routes. | P0 |
| REQ-CT-009 | Merchant-to-settlement mapping is stored (`merchant_settlement_map`) and exposed as an opaque alias only (`SANDBOX_MERCHANT_PRIMARY`); no PayPal account identifier, email, or secret is stored. | P0 |
| REQ-CT-010 | Seeding is idempotent and safe on cold start and concurrent starts; a seed-hash drift creates a NEW `catalog_version` rather than mutating old price rows. | P0 |
| REQ-CT-011 | Operator-only `POST /admin/seed` and `POST /admin/reset`, disabled unless `PS_CATALOG_ADMIN_ENABLED=true`, using a separate write-capable DB connection. Every call logged with actor. | P0 |
| REQ-CT-012 | Per-merchant refund-policy SEEDS (illustrative parameters) are stored and readable at `GET /merchants/{id}/refund-policy-seed`. They are reference data; the policy engine in `resolution` stays authoritative (see spec conflicts). | P1 |
| REQ-CT-013 | All endpoints require a valid internal JWT (`aud=catalog`) and enforce a per-endpoint caller/role allowlist; deny by default (ADR-006). | P0 |
| REQ-CT-014 | `/healthz` (liveness) and `/readyz` (DB reachable + seed present + version row) per overview. | P0 |
| REQ-CT-015 | OpenAPI 3.1 contract committed under `contracts/openapi/catalog.yaml`; CI fails on undeclared diff (ADR-008). | P0 |
| REQ-CT-016 | UI/API responses and docs label data "SIMULATED / seeded catalog / sandbox only". Response header `X-Data-Label: simulated-seed`. | P1 |
| REQ-CT-017 | Free-text filter `q` and cursor pagination on `/items`. | P2 |
| REQ-CT-018 | Optional outbox events `catalog.seeded` / `catalog.reset` for audit of admin actions (service-map says "Events: none"; see spec section 12). | P2 |

## 3. Non-goals
- Ranking, search relevance, recommendations, cart logic, inventory/stock, shipping or tax calculation, merchant onboarding, images/CDN, multi-currency, any write path used by buyers or merchants at runtime (service-map NOT-its-job list).
- Deciding refund eligibility (resolution owns policy decisions).
- Sanitizing text for LLMs (that is the shared `llm-gateway` package inside the `ai` process; catalog only labels text untrusted and serves it verbatim).
- Claiming real products, real merchants, real prices, or real settlement separation.

## 4. Metrics (measure, then report; no targets invented)
| metric | how | note |
|---|---|---|
| Price-integrity test pass rate | CI: all fixtures where client price != DB price | must be 100% (binary gate) |
| Resolve responses sourced from DB | code review + test that request-body prices never alter output | binary |
| Injection fixture presence | CI asserts PW-001 exists, flagged, description unchanged | binary |
| Contract drift | CI OpenAPI diff | zero undeclared |
| Resolve latency, cold-start-to-first-200 | measured in Profile A vs B during week 4 | targets unknown (I) |
| Seed idempotency | run seed 2x and concurrently, version count unchanged | binary |

## 5. Risks
| risk | impact | mitigation |
|---|---|---|
| Catalog down or cold (Profile A) | checkout cannot re-price, blocks (overview failure table) | Profile B co-location in `core`; warm-up script; callers retry idempotent GET/POST resolve with backoff |
| Someone adds a writable runtime path | breaks price authority | read-only DB role; admin path separated; test enumerates routes for mutating verbs |
| Descriptions reach an LLM unwrapped | injection (threat model risk 5) | `text_trust` field; wrapper lives in llm-gateway; integration test with PW-001 |
| Fixture flag leaks to model | model sees a tell, demo is dishonest, or agent gates on it | flag in separate table and view, operator-only route; test that public JSON has no fixture key |
| Seed drifts between environments | different prices in demo vs CI | seed hash + `catalog_version`; readyz exposes version |
| Pinned version prices disappear | old carts cannot be validated | price rows append-only, never deleted by reset |
| Reset wipes version history mid-demo | breaks in-flight carts | reset re-applies seed as new version, does not delete history (spec section 6) |
| Honesty: presenting seeded catalog as real | credibility | labels in API header, docs, UI |
