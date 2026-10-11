# triage-ai: PRD

Date 2026-10-10. Labels: V verified, VC vendor/secondary, I inference/unverified. Sources: `00-context-brief.md`, `architecture/{service-map,adr,overview,agent-and-mcp-design,llm-cost-and-latency,threat-model,deployment-zero-cost}.md`. Where those conflict, service-map.md and adr.md win; conflicts are logged in `spec.md` section 14.

## 1. Purpose (one paragraph in bullets)
- Turn untrusted free text (buyer problem report, carrier notes) into a constrained, validated signal for the deterministic `resolution` service.
- Three functions only: `classify` (enum + confidence), `draft` (gated message with placeholders), `brief` (read-only reviewer brief with inconsistency flags).
- AI NEVER decides money (V, brief section 5). Output is data: an enum, a confidence, short gated text, flags.
- Fail closed: any error, schema failure, low confidence, injection suspicion -> `HUMAN_REVIEW` with a code-built static brief.
- Runs inside the `ai` process in Profile B (ADR-005, overview section 8); calls the shared `llm-gateway` package (not a service) for all model access.

## 2. Users and consumers
| consumer | uses | notes |
|---|---|---|
| `resolution` (only caller) | `/classify`, `/draft`, `/brief` | sequences the three calls; no call triggers another |
| Merchant reviewer (via web -> gateway -> resolution) | brief + flags | never calls triage-ai directly |
| Judges / readers | printed eval report + injection scenes | the proof AI is not decorative |
| `audit` | `triage.completed` events | hashes only |

## 3. Requirements
Priority: P0 must ship for demo; P1 should; P2 nice. Each REQ has a test in `test-plan.md` (ID in brackets).

### Classification
- REQ-TA-001 (P0) `POST /classify` accepts buyer text plus server-derived order facts and returns `category` in {LATE, LOST, DAMAGED, WRONG_ITEM, NOT_AS_DESCRIBED, OTHER}, `confidence` in [0,1], `route` in {PROCEED, HUMAN_REVIEW}, `reasons[]`. [U-CLS-*]
- REQ-TA-002 (P0) Output validated by pydantic with `extra="forbid"`; unknown keys, wrong types, out-of-enum values = schema failure = fail closed. [U-SCH-*]
- REQ-TA-003 (P0) Any of: LLM error/timeout, schema failure, `confidence < PS_TRIAGEAI_MIN_CONFIDENCE`, `injection_suspected`, `evidence_quote` not a substring of input, kill switch on, budget exhausted, breaker open -> `category=OTHER, confidence=0.0, route=HUMAN_REVIEW`. [U-FC-*]
- REQ-TA-004 (P0) `PS_TRIAGEAI_MIN_CONFIDENCE` default 0.7 is labelled UNVALIDATED (I). A calibration procedure on the labelled eval set is a required deliverable before the config freeze. [E-CAL-1]
- REQ-TA-005 (P1) Deterministic consistency check between category and the simulated carrier timeline; mismatch adds a `reasons[]` code and forces `HUMAN_REVIEW` (never an auto-deny). [U-CON-*]

### Drafting
- REQ-TA-010 (P0) `POST /draft` returns `{subject, body}` using ONLY allowlisted placeholders (`{amount}`, `{order_ref}`, `{date}`, `{buyer_name}`); the server (resolution) fills them. The model never sees or emits amounts. [U-DRF-*]
- REQ-TA-011 (P0) Regex gate on every draft: no URLs, no emails, no digits/currency amounts, no phone numbers, no instruction-like phrases, no unknown placeholders. Normalization (NFKC, zero-width strip) runs before matching. [U-GATE-*]
- REQ-TA-012 (P0) Gate reject (or any LLM failure) -> deterministic per-category template, response flagged `source=template`. The system always returns a usable draft. [U-GATE-fallback]
- REQ-TA-013 (P1) Neutral wording rule: no accusation language ("fraud", "suspected"); enforced by the prompt and a deny-list in the gate (threat-model section 7). [U-GATE-tone]

### Reviewer brief
- REQ-TA-020 (P0) `POST /brief` returns a read-only brief `{summary, key_facts[], inconsistency_flags[], open_questions[]}`. No action fields exist in the schema. [U-BRF-*]
- REQ-TA-021 (P0) `key_facts[].value` is filled by code from the request's server facts; the model only chooses which field names to surface. A model cannot misquote an amount, date, or status. [U-BRF-facts]
- REQ-TA-022 (P0) Inconsistency flags between buyer text and tracking timeline come from a deterministic rule set (authoritative) plus optional model-suggested flags that must cite real `event_id`s (else dropped). Each flag shows `origin` = `rule` | `model`. [U-INC-*]
- REQ-TA-023 (P0) Brief summary passes the URL/email/amount gate; on failure or LLM error the brief is built entirely by code from facts (`source=template`). [U-BRF-fallback]

### Safety, config, ops
- REQ-TA-030 (P0) All untrusted text is delimited in `<untrusted source=... id=...>` blocks after sanitizing and length-capping; system prompt carries rules only. Documented as reducing, not eliminating, injection risk. [U-INJ-*, I-CORPUS]
- REQ-TA-031 (P0) No PayPal credentials, no outbound calls to other services, no DB access to money tables. Only egress: the `llm-gateway` package -> provider. Own schema `triage` only. [S-ISO-*]
- REQ-TA-032 (P0) Auth: internal JWT (`aud=triage-ai`), caller allowlist = `resolution` only; deny by default. [S-AUTH-*]
- REQ-TA-033 (P0) `PS_TRIAGEAI_LLM_ENABLED=false` (env or DB flag) -> every endpoint returns its deterministic fallback; the full protect -> refund flow still passes. [E2E-NOLLM]
- REQ-TA-034 (P0) Provenance on every response: `source` in {live, cached, template, rules}, `model`, `prompt_version`, `cached_at` when cached. UI shows a "CACHED RESPONSE" badge; cache is never presented as live. [U-CACHE-*]
- REQ-TA-035 (P0) Structured log per call with `trace_id`, hashes, tokens, latency, status, flags. No raw buyer text in logs; no emails/names/tokens. [U-LOG-*]
- REQ-TA-036 (P0) Emit `triage.completed` (hashes + category + confidence + flags, no raw text) to audit through the outbox. [U-EVT-*]
- REQ-TA-037 (P1) Max 6 LLM calls per case lifetime across all AI tasks (llm-cost section 2); triage-ai uses at most 3 (classify, draft, brief) plus no retries beyond 1. [U-BUD-*]

### Evaluation
- REQ-TA-040 (P0) Labelled eval set of 40 synthetic messages (spec section 11) in `evals/triage/`, runner script, committed results file with model id + date. [E-RUN-*]
- REQ-TA-041 (P0) Printed eval report (accuracy, fail-closed rate, injection outcomes, gate catch rate, reliability table) committed and linked from README; re-run on any prompt or model change. [E-REPORT]
- REQ-TA-042 (P0) Injection corpus (the 10 adversarial eval items plus gate unit corpus) runs in CI on a stub LLM and in the eval on the live model. [I-CORPUS]
- REQ-TA-043 (P1) Fault-injection suite: forced timeout, malformed JSON, extra keys, 429, breaker open -> 100% HUMAN_REVIEW/template. [U-FC-*]

## 4. Non-goals
- Not deciding refund, amount, currency, merchant, capture_id, or approval. Not denying any claim. (Never-AI-controlled list, threat-model section 6.)
- Not sending messages (drafts are returned; resolution/human releases them; email is out of scope, service-map merges).
- Not calling other services, PayPal, MCP, or the DB tables of other services. Not fetching URLs.
- Not fraud scoring, buyer reputation, or velocity logic (policy engine in resolution).
- Not multilingual quality guarantees: non-English input is tested only to confirm it routes to HUMAN_REVIEW or OTHER.
- Not real carrier data: timelines are SIMULATED CARRIER.
- Not a general chat or agent: no tools, no loops, no memory across calls.
- Not a measured production accuracy claim (small synthetic set).

## 5. Success metrics (our own heuristics, I; not industry standards)
Small n: report counts (e.g. "22 of 25"), not percentages with false precision. Thresholds are starting gates, tuned after the first run, and any change is recorded in the report.
| metric | definition | starting gate (I) |
|---|---|---|
| schema-valid rate | share of live calls whose raw model output passes pydantic strict | >= 95% (matches agent doc heuristic) |
| clean accuracy | correct enum on 25 clean category items | >= 80% (agent doc heuristic) |
| ambiguous routing | share of the 5 OTHER/ambiguous items ending HUMAN_REVIEW or OTHER | >= 70% |
| injection unsafe outcomes | released draft with URL/amount, or output that follows an injected instruction into a money-implying result | 0 (hard gate) |
| fail-closed rate on faults | fault-injection calls ending HUMAN_REVIEW/template | 100% (hard gate; deterministic) |
| gate catch rate | adversarial drafts blocked by regex gate | 100% of corpus (hard gate; corpus is ours, so it proves regressions, not coverage) |
| inconsistency detection | seeded inconsistent (text, timeline) pairs flagged | tracked as counts vs seeded truth; no pass number invented |
| p95 latency per function | measured, not promised | L1 <2 s classify, L2 <5 s draft, brief async (I, llm-cost targets) |
- Live demo-level metrics: HUMAN_REVIEW rate, cache-hit rate, fallback rate (dashboard `/ops/llm`).

## 6. Risks
| risk | likelihood / impact (I) | mitigation |
|---|---|---|
| "AI looks decorative": judges see an enum classifier that policy could replace with keywords | High / High | (1) Inconsistency detection between buyer text and tracking timeline in the brief: the thing a keyword rule cannot do alone. (2) Printed eval with accuracy, fail-closed rate, injection outcomes, and a keyword-baseline side-by-side (CI side-by-side, test-plan section 6) so the AI's added value is a measured number or an honest "no gain". (3) Demo scene: injected carrier note -> HUMAN_REVIEW. (4) Never overclaim: if baseline ties, say so and justify AI by drafting/brief |
| Keyword baseline beats LLM on clean categories | Med / Med | Report it; keep LLM for ambiguous/free-text and brief; baseline remains the fallback path |
| Model misclassifies and sends a wrong signal | Med / Low-Med | Category is only an input; policy cross-checks carrier DB; low confidence/injection -> human; AI never denies |
| Prompt injection via buyer text or carrier note | Med / Med | Delimiting + strict schema + enum-only + gate + HUMAN_REVIEW. Not injection-proof; do not claim |
| Self-reported confidence is uncalibrated; 0.7 is arbitrary | High / Med | Marked UNVALIDATED; calibrate on eval set; record reliability table; threshold is config |
| Free-tier quota / 429 during judging | Med / Med | llm-gateway caps, fallback chain, cache with badge, template fallback; never blocks money |
| Gemini free-tier content may train models (V) | High / Low | Synthetic demo text only; README note |
| Eval set too small / author-labelled bias | High / Med | State n and that one author labelled; second-reader pass for the 40; publish the file |
| Prompt/model drift across free-tier model changes | Med / Med | Pin model ids, `prompt_version`, freeze by 2026-11-05 (llm-cost section 6), re-run eval on any change |
| Gate false positives degrade drafts | Med / Low | Template fallback; track template rate in report |
| Scope creep into decision-making | Low / High | Schemas contain no amount/action fields; code review checklist; import lint (no money modules) |

## 7. Dependencies and assumptions
- `llm-gateway` shared package provides: provider routing, `complete_json`, budget guards, circuit breaker, `llm_cache`, kill switch, per-call telemetry. triage-ai does not talk to providers directly (conflict note: llm-cost doc describes gateway as a service; here it is a package, spec section 14).
- `resolution` sends all facts in the request body (trusted facts and untrusted text in separate fields).
- `audit` receives events by outbox push.
- Model choice and exact free-tier quotas: unknown until read in AI Studio / Groq console (I).

## 8. Definition of done (pointer)
See `test-plan.md` section 9. Short: all P0 REQs green, eval report committed with model id + date, `PS_TRIAGEAI_LLM_ENABLED=false` end-to-end passes, injection corpus clean, deployed in the `ai` process and warm-up-checked.
