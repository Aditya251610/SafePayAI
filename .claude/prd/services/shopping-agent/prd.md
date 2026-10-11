# shopping-agent: PRD

Labels: V verified, VC vendor claim, I inference/assumption/our own target. Date 2026-10-10. Sources: `../../00-context-brief.md`, `../../architecture/*.md`. On conflict, `service-map.md` and `adr.md` win; conflicts are listed in `spec.md` section 14.

## 1. Role (one paragraph)
shopping-agent turns buyer intent text plus a read-only mandate summary and a catalog slice into a schema-validated cart proposal (`{sku, qty}[]` + display-only rationale), and offers an advisory intent-fit verdict that can only tighten. It is a bounded proposer, not a buyer: sole tool `propose_cart` (an output-schema carrier, not an executable), no PayPal credentials, no write path to any money table, no memory between calls. Money truth stays deterministic: `checkout` re-prices from `catalog`, `mandate` hard-checks. It runs inside the `ai` process in Profile B and calls the shared `llm-gateway` package (a package in that process, not a service).

## 2. Why it exists (and why it is small)
- Agentic Commerce prize fit, with the Mandate and SafePayAI loop as the hero (brief section 1). Budget: ~30% of demo runtime (~50s of 2:45) — confirmed, D8, 00-platform-prd.md: the agent segment flows directly into the real PayPal order/approve/capture, demonstrating agentic AI and PayPal-centrality in the same beat.
- Generic shopping agents and auto-buyers are saturated hackathon ideas (I, brief section 4). So the agent is shown only as "the thing the Mandate constrains".

## 3. Users
- Buyer (demo account): types intent, reviews proposed cart. Judge: watches the agent being blocked, not just succeeding.
- checkout service (machine caller of `/intent-fit`).

## 4. Requirements

| ID | Requirement | Priority |
|---|---|---|
| REQ-SA-001 | `POST /propose` returns a cart proposal built only from SKUs in the supplied catalog snapshot, quantities integers 1..5, max 5 lines | P0 |
| REQ-SA-002 | Model output is validated against a strict pydantic schema (`extra=forbid`); any schema failure after 1 retry returns `NO_PROPOSAL`, never partial output | P0 |
| REQ-SA-003 | Output contains no price, total, merchant, currency, URL or payment field; any such field fails validation. The caller (checkout) re-prices | P0 |
| REQ-SA-004 | Sole tool is `propose_cart`; service holds no PayPal credential, no MCP access, no money-service client, no DB grant outside its own `agent` schema | P0 |
| REQ-SA-005 | Buyer intent, catalog titles/descriptions and mandate intent text are treated as untrusted data in delimited blocks; injected instructions must not change which tool/schema is used | P0 |
| REQ-SA-006 | `POST /intent-fit` returns `PASS | NEEDS_BUYER_CONFIRMATION | REJECT_WITH_REASON`; any error, timeout, low confidence or `LLM_ENABLED=false` returns `NEEDS_BUYER_CONFIRMATION` (never PASS) | P0 |
| REQ-SA-007 | `/intent-fit` is only meaningful after hard checks pass; the service cannot return a verdict that clears a hard block (it has no hard-block input and its response is documented as tighten-only) | P0 |
| REQ-SA-008 | Kill switch `LLM_ENABLED=false` yields the form-driven fallback for `/propose` and `NEEDS_BUYER_CONFIRMATION` for `/intent-fit`, with no provider call | P0 |
| REQ-SA-009 | Form-driven fallback (category + budget + quantity inputs, deterministic matcher) so the demo never dead-ends | P0 |
| REQ-SA-010 | Every response states `source`: `live | cached | form`; cached responses carry the badge text "CACHED RESPONSE (recorded from live model run <date>)"; live responses carry model name and latency | P0 |
| REQ-SA-011 | Pre-warmed pinned cache for scripted demo inputs; cache never bypasses downstream re-pricing or checks | P1 |
| REQ-SA-012 | Persist `proposal_log` (prompt hash, model id, output, validation result, latency) and emit `cart.proposed` via outbox to `audit`; store hashes, not raw buyer text, in logs | P0 |
| REQ-SA-013 | Inputs bounded: intent <= 500 chars; total prompt input <= 1,500 tokens (truncate untrusted text to 1,000 chars); max output 400 tokens (cart), 200 (fit) | P0 |
| REQ-SA-014 | Honour llm-gateway budgets and breaker: per-cart cart<=2 and fit<=1 LLM calls; global daily cap at 70% of tightest provider cap; 429/402 never retried | P0 |
| REQ-SA-015 | Auth: every endpoint requires an internal JWT with `aud=shopping-agent`; deny by default; buyer can only propose against own mandate | P0 |
| REQ-SA-016 | Structured JSON logs with `trace_id`, `prompt_version`, `provider`, `model`, `attempt_no`, `cache_hit`, `status`; no secrets, no raw buyer text | P0 |
| REQ-SA-017 | Eval suite of ~20 labelled cart prompts + ~12 intent-fit pairs, committed with runner and results; rerun on any prompt/model change | P0 |
| REQ-SA-018 | `/healthz` and `/readyz` (DB reachable, config valid, gateway breaker state; no live LLM call in readiness) | P1 |
| REQ-SA-019 | Output rationale is display-only: escaped by UI, never parsed, never forwarded to PayPal or into money requests | P0 |
| REQ-SA-020 | OpenAPI 3.1 contract committed under `contracts/openapi/` and diffed in CI | P1 |

## 5. Non-goals
- No autonomous capture: the service never creates an order, approves, or captures; buyer confirms cart and clicks approve in PayPal.
- No multi-merchant search or ranking: only the seeded catalog (~12 items, 3 virtual merchants) supplied by `catalog`.
- No chat memory: each call stateless, no history, no conversation endpoint. (Agent "chat" UI, if any, is a thin client re-sending a fresh intent; first thing cut, see sprint-tasks.)
- No price negotiation, price tracking, coupon search, web access, retrieval over external content.
- No refund, triage or case logic (that is `triage-ai` / `resolution`).
- No claims of "injection-proof", "PayPal-backed", real carrier data, or real money.

## 6. Success metrics (all targets are ours, label I; report counts with small-n caveat)
| Metric | Target | Source of target |
|---|---|---|
| Schema-valid rate, cart eval | >= 95% (>= 19 of 20) | brief section 3 target; agent-and-mcp-design 1a |
| Normal-prompt acceptable-cart rate after deterministic validation | >= 85% (>= 9 of 10 normal) | agent-and-mcp-design 1a heuristic |
| Unsafe cart reaching order creation under adversarial prompts | 0 | property of checkout/mandate checks |
| Intent-fit: clear-mismatch returned PASS | <= 1 of the mismatch cases | agent-and-mcp-design 1b heuristic |
| Cart p95 latency, live | <= 8 s total incl. fallback | llm-cost-and-latency wall budget |
| Demo never dead-ends | 100% of scripted inputs have a live, cached or form path | design rule |
| Agent screen time in video | ~30% (~50s of 2:45) | confirmed, D8 |
| Live-model calls per demo run | unknown until measured; budget table in llm-cost-and-latency | I |

## 7. Risks and mitigations
| Risk | Mitigation |
|---|---|
| **Reads as a generic buying agent** (saturated idea, hurts originality score) | Framing in UI/video: the agent is "inside the Mandate"; every agent screen shows the Mandate summary beside the cart; show the agent being BLOCKED (over cap, wrong merchant, injected catalog text) before showing it succeeding; agent time capped ~30%; narration says "proposes only, server re-prices, buyer signs, PayPal approves"; no autonomous purchase scene; hero moment stays the SafePayAI refund |
| Free-tier LLM 429/outage during judging or recording | llm-gateway breaker + fallback provider, pinned badged cache, form-driven fallback, UI text "AI assist paused (free-tier limit) - using form mode" |
| Prompt injection via catalog text or intent | Delimited untrusted blocks, forced schema, enum/ID-only output, deterministic downstream blocks; claim only "checks block unsafe carts", never "injection-proof" |
| Cached output mistaken for live | Mandatory `source` field and on-screen badge; never present cache as live |
| Free-tier data used for provider training (Gemini, V) | Seeded/synthetic data only; "demo data only" note |
| Cold start (Render free sleep ~1 min, V) on first propose | Profile B (`ai` process warm via pinger), warm-up script, "waking server" UI state |
| Scope creep into chat/memory | Non-goals above; day-14 cut line |
| Sprint slip leaves eval unrun | Eval runs from week 2; model freeze 2026-11-05 (llm-cost doc) |

## 8. Open questions
- Exact Gemini free RPM/RPD for chosen models: unknown, read in AI Studio.
- Final catalog SKUs (eval prompts use placeholders until seed lands).
- Whether `llm_cache` / budget counters live in an `llm` schema shared by the ai process (see spec conflicts).
