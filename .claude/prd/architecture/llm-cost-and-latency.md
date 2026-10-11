# LLM cost, latency and guardrails (zero-cost hackathon deploy)

Date 2026-10-10. Labels: V verified (fetched today), VC vendor/secondary, I inference/unverified. Budget target: $0.00 spend. No card on any LLM account unless the card-less path is exhausted.

## 0. Verified free-tier facts

| Provider | Fact | Label | Source |
|---|---|---|---|
| Gemini API | Free tier ("Free of charge") exists for Gemini 3.8 Flash, 3.6 Flash, 3.5 Flash-Lite, 3.1 Flash-Lite, 2.5 Pro/Flash/Flash-Lite, Gemma 4. No free tier for 3.1 Pro Preview. Free-tier content "used to improve our products" (do not send real PII; seeded demo data only). | V | https://ai.google.dev/gemini-api/docs/pricing |
| Gemini API | Limits are per PROJECT, not per key (extra keys do not help); daily quota resets midnight Pacific; preview/experimental models have stricter limits; auto tier upgrade with spend. | V | https://ai.google.dev/gemini-api/docs/rate-limits |
| Gemini API | Exact free RPM/TPM/RPD per model: page does not publish them; read in AI Studio rate-limit page. Treat as unknown. | I | https://aistudio.google.com/rate-limit |
| Groq | Free plan table lists gpt-oss-120b / gpt-oss-20b / qwen3.8-27b at 30 RPM, 1K RPD, 8K TPM, 200K TPD. Page is ambiguous whether this table is Free or Developer plan; confirm in console. 429 + `retry-after` header on excess. | V (numbers) / I (plan attribution) | https://console.groq.com/docs/rate-limits |
| OpenRouter | `:free` models: 20 RPM; 50 req/day if <$10 credits ever bought, 1,000/day if >=$10. Negative balance gives 402 even on free models. 429 on excess. | V | https://openrouter.ai/docs/api-reference/limits |
| Cloudflare Workers AI | 10,000 Neurons/day free; Workers Free has no overage ("further operations will fail"); resets 00:00 UTC. Paid is $0.011/1K Neurons. | V | https://developers.cloudflare.com/workers-ai/platform/pricing/ |
| Hugging Face Inference Providers | Free users get NO monthly credits; pay-as-you-go only after buying credits. PRO gets $2/month. Not a free option. | V | https://huggingface.co/docs/inference-providers/pricing |
| Anthropic / OpenAI | New-account credit (~$5) reports conflict across unofficial blogs; some say card required. Do not plan on them. Use only as optional last-resort, hard-capped in console. | I (unverified; aggregator blogs) | search results, no primary source |

## 1. Model-routing plan per AI task

Rule: one thin `llm-gateway` service (OpenAI-compatible calls) owns all provider keys and routing. Other services never call a provider directly. Model IDs are config, not code.

| Task | Primary | Fallback 1 | Fallback 2 (always works) | Why | Latency class |
|---|---|---|---|---|---|
| Cart proposal (structured JSON, SKU ids + qty) | Gemini Flash-class (free) w/ JSON schema output | Groq gpt-oss-120b (JSON mode) | Deterministic form-driven cart (buyer picks items from the 12-item catalog; keyword/category matcher) | Needs reliable schema; target >=95% valid on 20-prompt eval (I) | L2: 1-4 s, timeout 6 s |
| Intent-fit check (advisory, tighten only) | Gemini Flash-Lite | Groq gpt-oss-20b | Skip -> result `NEEDS_BUYER_CONFIRMATION` (fail toward more friction, never PASS) | Small enum output, cheap | L1: <2 s, timeout 4 s |
| Triage classification (enum + confidence) | Groq gpt-oss-20b (fast, 30 RPM V) | Gemini Flash-Lite | Keyword rules -> else `HUMAN_REVIEW` | Short in/out; speed matters on stage | L1: <2 s, timeout 4 s |
| Message drafting | Gemini Flash | Groq gpt-oss-120b | Static templates (no LLM) | Quality > speed; regex gate (no URLs/amounts) after | L2, timeout 6 s |
| Reviewer brief (read-only) | Gemini Flash | Groq gpt-oss-120b | Template summary of facts from DB | Async, off critical path | L3: up to 10 s, async |
| Shadow/eval only | OpenRouter `:free`, Workers AI | n/a | n/a | Spare quota; never prod (see 6) | async |

- Latency classes (I, set as targets, measure in telemetry): L1 <2 s, L2 <5 s, L3 async.
- Cloudflare Workers AI and OpenRouter are held OUT of the prod chain by default: OpenRouter free daily cap (50/day without $10, V) is too small; Workers AI 10K Neurons/day is shared with nothing else but model availability is I. Promote only after eval passes.
- Free-tier data may train provider models (Gemini V): send only seeded catalog and synthetic buyer text during recording/judging; show a "demo data only" note.

## 2. Hard budget guards (enforced in llm-gateway, not callers)

| Guard | Value (config, initial) |
|---|---|
| Per-case LLM calls | max 6 per case_id lifetime (cart 2, fit 1, triage 1, draft 1, brief 1); 7th -> deterministic fallback |
| Per-IP | 20 LLM calls/hour, 60/day (token bucket); header-IP behind proxy trusted only from the platform |
| Per-session/mandate | 15 calls |
| Global per-day | 70% of the tightest provider daily cap (e.g. 700 of Groq 1K RPD, V cap); budget counter in DB, resets per provider's reset clock (Gemini midnight PT, CF 00:00 UTC) |
| Max tokens | input <= 1,500 tokens (truncate untrusted text to 1,000 chars); max_output 400 (cart/fit/triage 200, draft 300, brief 400) |
| Timeout | per attempt per table above; total wall budget per request 8 s incl. fallbacks; 1 retry max on same provider ONLY for 5xx/timeout, never on 429/402 |
| Retry cap | 1 provider retry + 2 fallback hops; no loops, no agentic tool loop > 1 turn |
| Circuit breaker | per provider: open after 3 failures in 60 s OR any 402 OR 2x 429 in 30 s; open 120 s then half-open with 1 probe; honor `retry-after` (Groq V, OpenRouter V) |
| Anomaly | >5x baseline req rate in 5 min (500% rule) -> trip global breaker, serve cached/deterministic only, alert (Discord/email webhook) |
| Kill switch | env `LLM_ENABLED=false` AND DB flag (flip without redeploy). Fails CLOSED: cart -> form-driven; fit -> NEEDS_BUYER_CONFIRMATION; triage -> HUMAN_REVIEW; drafts -> templates; brief -> fact template. Gateway unreachable = same as kill switch |
| Spend | No payment method on any LLM provider; Gemini project kept on free tier (auto-upgrade risk, see 8) |
| Auth | Gateway accepts only internal service tokens; no browser-direct calls; no LLM key in frontend |

Estimated cost: $0 per 1M tokens on free paths (V free tiers above); paid-equivalent reference unknown/not needed. If forced to paid: Workers AI $0.011/1K Neurons (V) is the only price verified today.

## 3. Caching and determinism

- Temperature 0 for cart, fit, triage; 0.3 for drafts/brief. Fixed `seed` where provider supports it (I; not all do), fixed system prompts versioned (`prompt_version` in every call and audit row).
- Cache key = sha256(task, prompt_version, model_id, normalized input, catalog_version). Store in DB table `llm_cache` (value, provider, created_at, `source`).
- Pre-warm: run all scripted demo inputs (cart prompts, 3-4 problem texts) once before recording; store in cache with `pinned=true`.
- On screen: cache hits show a badge "CACHED RESPONSE (recorded from live model run <date>)". Never present cache as live. Live calls show model name + latency chip.
- Cart cache is advisory only: server still re-prices and runs all mandate checks every time, so cached output cannot bypass money checks.
- Non-demo inputs: cache identical normalized inputs for 24 h to cut quota burn (I).
- Output validated with strict schema (pydantic); invalid after 1 repair-free retry -> fallback, not loop.

## 4. Demo-day resilience

- T-24 h: run `llm-smoke` (all 5 tasks x 2 providers); record result; pin cache. T-1 h: re-run; check remaining daily quota per provider.
- Recording: use live path first; if provider 429/down, the breaker opens and chain falls to second provider within the 8 s budget; if all down, scripted inputs serve pinned cache (badged) and unscripted inputs use form-driven intent/HUMAN_REVIEW. The video never blocks on an LLM.
- Judging (live site, unknown traffic): global cap at 70% leaves headroom; per-IP caps stop one judge draining quota; when cap hit UI shows "AI assist paused (free-tier limit) - using form mode", not an error.
- Keep two recorded takes: one live, one with cache (labelled) so an outage during editing does not matter.
- README must state: AI features degrade to deterministic mode; money flow works with LLM off. Test with `LLM_ENABLED=false` end to end before submission (must pass full protect -> refund flow).
- Do not run evals/shadow jobs on judging day (quota shared per project/org).

## 5. Telemetry and dashboard

Per LLM call, one structured log row (table `llm_calls`, also JSON log line):
`trace_id` (propagated from gateway request id through all services and into audit log reference), `case_id`, `mandate_id`, `task`, `prompt_version`, `provider`, `model`, `attempt_no`, `fallback_reason`, `cache_hit`, `input_tokens`, `output_tokens`, `latency_ms`, `status` (ok/timeout/429/402/5xx/schema_fail), `schema_valid`, `est_cost_usd` (0 on free; recorded as "list-price-equivalent" if known else null), `quota_remaining` (from provider headers where given, V for Groq/OpenRouter), `client_ip_hash`, `kill_switch_state`. No raw user text stored (hash + length) to avoid PII; store prompts only for seeded demo inputs.

Dashboard (single page `/ops/llm`, admin-only, SQL views; no extra paid tool):
- Tiles: calls today per provider vs cap; breaker state per provider; kill switch state; cache hit rate; fallback rate.
- Charts: p50/p95 latency per task; schema-valid rate per task; 429/402 count per hour; calls per case histogram (flag >6).
- Alerts (webhook): breaker open, daily budget >70%, anomaly 5x, schema-valid <90% over 50 calls.

## 6. Shadow-testing plan (no money paths)

- Eval sets: cart (20 prompts, target >=95% valid, from brief), triage (labelled problem texts across the 6 enum values, incl. adversarial/injection strings), fit (pass/confirm/reject set). Label by hand; keep in repo.
- Method: offline replay first (script, not live traffic). Optional online shadow: duplicate 5% of NON-demo requests async to a candidate model via a separate queue with its own tiny budget (e.g. 20 calls/day); result is logged only, never returned, never written to case state or audit chain, no access to PayPal services.
- Scoring (fixed before testing): +5 schema-valid; +3 correct enum / valid SKUs; +2 under latency target; -10 hallucinated SKU / wrong merchant; -10 any URL or amount in draft; -20 a triage that would auto-clear a case that humans label HUMAN_REVIEW. Promote candidate only if score >= baseline over >= 100 eval items AND zero -20 events. Promotion is a config change reviewed by a human before submission freeze; auto-promotion disabled in prod.
- Candidates: Gemini 3.x Flash variants, Groq gpt-oss/qwen3.8, OpenRouter `:free`, Workers AI. Freeze models by 2026-11-05.

## 7. Rules: LLM never on the money critical path

- No PayPal order create, capture, refund, approval link, or amount calculation waits on an LLM. Those paths call zero LLM code; lint/test asserts no import of gateway client in `bids/payments/refund` modules (equivalent for this product: order, capture, refund, mandate-check services).
- Cart: LLM output is only a proposal; user sees it, then deterministic checks run. If LLM times out (6 s) the buyer proceeds via form; no automatic retry loop.
- Triage/draft/brief run async via a job; a refund offer is produced by deterministic policy on case facts, and is never blocked waiting for AI text (use template if draft not ready within 4 s).
- LLM outputs are data: only enum values and catalog IDs are consumed; free-form text never changes amounts, merchants, or states except TRIAGED label. Triage low confidence (<0.7, I initial) or schema fail -> HUMAN_REVIEW.
- Synchronous LLM calls only on UI-interactive steps (cart, fit) with total budget 8 s; everything else async. Refund executor reads no LLM field.
- LLM service has no PayPal credentials, no network route to PayPal, no DB write role beyond `llm_calls`/`llm_cache`.

## 8. Cost cliff list (where free can silently bill or break)

- Gemini: tier auto-upgrades "as usage and spending grow" (V); linking a billing account to the Google Cloud project can move it to paid. Use a project with NO billing account; verify AI Studio shows "Free tier".
- Gemini: preview models stricter and may change/disappear; a model with no free tier (e.g. 3.1 Pro Preview, V) returns paid billing or errors. Allowlist model IDs in gateway.
- Gemini: per-project limits; more keys in same project do not add quota (V). Multiple projects to dodge limits may violate ToS (I) - don't.
- Gemini free-tier content may train models (V) -> privacy, not billing.
- OpenRouter: any purchased credit makes paid models reachable; a non-`:free` model ID typo bills. Gateway rejects model IDs not ending `:free` on that provider. Negative balance blocks even free (V). 50/day cap without $10 (V).
- Groq: free-vs-Developer table ambiguity (V); upgrading plan = billing. Confirm plan in console (I).
- Cloudflare: Workers Free hard-fails (V) but upgrading to Workers Paid bills $0.011/1K Neurons; keep free plan. Neuron cost per model varies (I).
- Hugging Face: no free credits for free users (V); routed requests bill your account once credits are bought.
- Anthropic/OpenAI: trial credits unverified (I); keys in env with auto-recharge OFF and monthly limit in console, or do not configure.
- Hosting-side: LLM retries multiply serverless invocations/egress; cap retries (section 2). Log volume on free log tiers (I).
- Public demo URL: bot traffic exhausts daily quota (denial of wallet becomes denial of service); per-IP caps + global 70% cap + kill switch.
- Secrets leakage in public repo -> key abuse; gitleaks, keys only in platform env.
- Quota-reset timezones differ (Gemini PT, Cloudflare UTC; V): budget counters must follow each provider's clock.

## Open items
- Read exact Gemini free RPM/RPD for chosen models in AI Studio and fill config (unknown).
- Confirm Groq console plan limits (table ambiguous).
- Verify Anthropic/OpenAI credit terms on official pages if wanted (currently I).
