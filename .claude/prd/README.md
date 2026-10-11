# PRD index: SafePayAI

Navigation only. Do not duplicate content here — every fact lives in exactly one doc below.

## 1. Project summary
SafePayAI is a buyer-signed purchase-protection product for the PayPal AI hackathon ("Build What's Next with PayPal and AI"), deadline 2026-11-12 noon PT (target submit 2026-11-10). A buyer-signed **Mandate** fixes what an agent may buy and what gets refunded if it doesn't arrive; a **bounded shopping agent** (LLM) only proposes carts inside that Mandate; a deterministic **SafePayAI loop** detects late/lost orders and refunds under pre-authorized terms. Protection is the hero (~70% of demo runtime); the agent is a bounded, secondary step (~30%). AI never decides money — deterministic, server-enforced policy does.

## 2. Start here (by role)
| If you are... | Read, in order |
|---|---|
| Project owner / reviewing the whole plan | `00-platform-prd.md` -> `sprint-plan.md` |
| Building a specific service | `00-context-brief.md` (once) -> that service's 6 docs in `services/<slug>/` -> the architecture docs its `spec.md` cites |
| An AI coding agent picking up any task | `architecture/agent-context-map.md` sec 1 (graph) -> your service's context pack in sec 5 -> only the files it names |
| Checking test or launch posture | `test-strategy.md` and `05-submission-and-launch-plan.md` |

## 3. Root docs
| Doc | Covers | Path |
|---|---|---|
| Context brief | Shared facts every doc assumes; read first, always | `00-context-brief.md` |
| Platform PRD | Vision, personas, user stories, features, requirements, non-goals, success metrics, D1-D10 decisions, release criteria, risk register | `00-platform-prd.md` |
| Market study | Competitive/market signal, no invented TAM | `01-market-study.md` |
| Product-market fit | PMF analysis, one-page answer | `02-product-market-fit.md` |
| Hackathon win probability | Calibrated odds, judging-criteria fit | `03-hackathon-win-probability.md` |
| User research & validation plan | Personas (hypotheses), interview plan, heuristics | `04-user-research-and-validation-plan.md` |
| Submission & launch plan | Devpost logistics, demo storyboard, timeline | `05-submission-and-launch-plan.md` |
| Sprint plan | Day-by-day plan Oct 10 - Nov 10, cut lines, freeze dates | `sprint-plan.md` |
| Test strategy | Master test IDs (security/chaos/spike/e2e/layers) referenced by every service test-plan | `test-strategy.md` |
| Workflow for AI coding agents | How one human directs AI agents through the ~30-day build | `workflow-for-ai-coding-agents.md` |

## 4. Architecture docs
| Doc | Covers | Path |
|---|---|---|
| Overview | System context, flows F1-F5, failure modes, consistency, contracts, process profiles | `architecture/overview.md` |
| Service map | Final 10 backend/edge services + 1 web app, endpoints, slugs | `architecture/service-map.md` |
| Service list | Plain slug list (matches folder names) | `architecture/service-list.txt` |
| ADRs | Short accepted architecture decisions (ADR-001...) | `architecture/adr.md` |
| Auth gateway | Demo-grade identity, sessions, internal tokens, return-URL binding | `architecture/auth-gateway.md` |
| Agent & MCP design | LLM principles, prompts/evals, own MCP server design over PayPal REST | `architecture/agent-and-mcp-design.md` |
| Threat model | Threats T1-T15+, controls, mapped tests | `architecture/threat-model.md` |
| LLM cost & latency | Free-tier LLM facts, spend-cap guardrails | `architecture/llm-cost-and-latency.md` |
| Deployment (zero cost) | Free-tier hosting/DB comparison and limits | `architecture/deployment-zero-cost.md` |
| Data architecture | One Postgres, schema-per-service, outbox pattern | `architecture/data-architecture.md` |
| Tech stack | Consolidated stack reference (no new decisions) | `architecture/tech-stack.md` |
| CI/CD & repo workflow | Public monorepo layout, pipeline, repo rules | `architecture/ci-cd-and-repo-workflow.md` |
| AI code audit plan | Static/security audit plan for AI-written code | `architecture/ai-code-audit-plan.md` |
| Pentest plan | Self-test plan, sandbox only | `architecture/pentest-plan.md` |
| Agent context map | **Load-bearing for AI agents**: entity graph, per-service "must read / must not need" context packs, glossary, naming conventions, re-sync log | `architecture/agent-context-map.md` |

## 5. Services (11 slugs, 6 docs each: prd, spec, api, deployment, test-plan, sprint-tasks)
| Slug | One-line role | Folder |
|---|---|---|
| api-gateway | Auth, sessions, internal tokens, routing/BFF, rate limiting | `services/api-gateway/` |
| mandate | Buyer-signed Mandate create/evaluate/revoke, deterministic hard blocks | `services/mandate/` |
| catalog | Seeded catalog (~12 items, 3 virtual merchants), authoritative pricing | `services/catalog/` |
| shopping-agent | Bounded LLM cart proposal + advisory intent-fit | `services/shopping-agent/` |
| checkout | Cart check orchestration, PayPal order create/capture, receipts | `services/checkout/` |
| paypal-adapter | Sole PayPal credential holder; REST wrapper + own MCP server | `services/paypal-adapter/` |
| tracking | Simulated carrier, demo clock, late/lost detection | `services/tracking/` |
| resolution | Case state machine, merchant policy, refund saga, reconciliation | `services/resolution/` |
| triage-ai | AI classification of problem reports, message drafts, reviewer briefs | `services/triage-ai/` |
| audit | Hash-chained append-only audit log + verify endpoint | `services/audit/` |
| web | Buyer + merchant UI, demo control panel | `services/web/` |

## 6. Decisions are final
D1-D10 (revoke semantics, buyer notification, merchant pre-auth wording, sponsor prize, hosting shape, judge credentials, protection window = 5 days, agent runtime share ~30%, product name "SafePayAI", merchant-cap-exceeded flow) are all **resolved and user-confirmed 2026-10-10**. See `00-platform-prd.md` sec 12. Do not reopen without a new user decision.

## 7. Known open items (genuinely unresolved as of 2026-10-10)
- Return URL into our own server is untested (platform-prd sec 11, A2).
- Sandbox refund PENDING outcome untested; only COMPLETED verified (A3).
- Product name trademark/name-clash check not yet done (D9 note).
- `authorization_ticket` vs callback validation still open (`agent-context-map.md` sec 6 glossary row, AMD#7).
- Free-tier hosting/LLM limits need re-verification before 2026-11-01 (`deployment-zero-cost.md`, `llm-cost-and-latency.md`).
- Official Devpost rules not yet fetched/re-read (platform-prd sec 11 dependencies, sec 13 release criteria).
- `architecture/agent-context-map.md` sec 8 itself: all re-sync rows are marked resolved — no open rows remain there.

## 8. What's next
Two phases remain before feature coding starts (per `sprint-plan.md` week 1):
1. **Wave 3 — consistency review** (current): cross-check all docs above for drift, close any remaining open items in sec 7.
2. **Wave 4 — scaffolding**: repo init, OpenAPI/event contracts (`contracts/openapi/*.json`, `contracts/events/*.v1.json`), docker-compose, CI skeleton (lint/test/gitleaks).

Only after wave 4 does real feature coding begin.
