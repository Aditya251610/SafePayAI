# Hackathon product selection

Date: 2026-10-10
Tags: hackathon, paypal, ai, product, selection

- Prefer a focused product with one clear user flow and one clear PayPal action.
- Avoid broad marketplace or platform ideas that require multiple systems and a long runway.
- Prefer server-enforced trust boundaries, not AI-driven money decisions.
- Build the demo around a real PayPal sandbox flow, not a polished mockup.
- The strongest wins come from product stories that reduce trust, uncertainty, or failure in money movement.

## Decision (2026-10-10): ARTIQ dropped, "SafePayAI" chosen
- ARTIQ (art auction, microservices) judged too big and PayPal too peripheral; a generic spend-capped shopping agent judged saturated.
- Chosen: SafePayAI = Delivery Watch + buyer-approved resolution loop (PayPal sandbox checkout -> tracking -> late/lost detected -> AI classifies/drafts only -> deterministic merchant policy -> buyer approves -> Payments v2 refund -> hash-chained audit log).
- Day-1 sandbox spike is a hard gate (capture, tracking write/read, partial refund, same PayPal-Request-Id replay). Fail -> concept dead or full-refund-only fallback.
- Honesty rules: carrier + clock are simulated; no "PayPal-backed" wording (say merchant-funded refund via PayPal); no conversion-lift or compliance claims; vendor/inferred baselines labelled.
- AI role must be provably real: ~30-message labelled eval incl. injection cases, printed accuracy + fail-closed rate.
- Deadline 2026-11-12 noon PT (secondary source; re-read Devpost rules); submit by Nov 10; feature freeze day 28.

## Update (2026-10-10): scope widened, user chose "SafePayAI + Mandate + bounded shopping agent"
- User will code with AI agents, so build volume is not the constraint; sandbox gating, 3-min demo, honesty, review time still are.
- Reranked 9 candidates; A (SafePayAI) and I (Agent Consent Rail) tied top; others killed (Hold Whisperer, Checkout Concierge, Cash-Flow Cockpit, Quote Court) or folded in.
- Final: buyer-signed Mandate (merchant allowlist, cap, expiry, pre-authorized refund terms) bounds a cart-proposing agent; SafePayAI loop pays out under the mandate. Agent has no PayPal credentials, never captures; seeded catalog (not Channel3); Render is the one sponsor prize.
- Caution: user's own prompt forbids a generic "agent that buys stuff" - mandate/protection is the hero, agent ~25% of demo runtime.
- Spike run 1 (2026-10-10, US buyer + IN business app, USD): token, order create + same-Request-Id replay, buyer approval (needs a real click; return_url redirect carries PayerID), capture COMPLETED, custom_id/invoice_id survive on capture, tracking add (201) / PATCH status (204) / read-back (<1s), partial refund COMPLETED, same-Request-Id replay returns original refund (also with a different amount), refund lookup, invalid token 401 all PASSED. Over-refund test was INVALID (hit DUPLICATE_INVOICE_ID) - redo with fresh invoice_id. Not yet tested: tracking statuses other than CANCELLED, cumulative refunds, webhooks, disputes. India buyer account could not pay USD; use US buyer.
- Spike run 2 (same capture, no new click): second partial refund OK; real over-refund -> 422 REFUND_AMOUNT_EXCEEDED; capture shows PARTIALLY_REFUNDED; two concurrent refunds with same Request-Id -> one 201 + one 409 (treat 409 as in-progress, reconcile by lookup, never retry blindly). TRACKING LIMITS: tracker default status SHIPPED; PATCH /status only works for CANCELLED (irreversible, CANNOT_PATCH_CANCELLED_TRACKER afterwards); ON_HOLD/DELIVERED PATCH -> 400 INVALID_PARAMETER_VALUE; setting status at creation is accepted but ignored (reads back SHIPPED); multiple trackers per capture allowed. => carrier status (late/lost/delivered) must live in OUR DB; PayPal tracking is only a 'tracking added' signal.
- Day-1 spike additions: buyer approve/capture programmatic vs one real click; custom_id/invoice_id survive to refund lookup; MCP vs REST; LLM cart JSON reliability >=95% on 20 prompts.

## Update (2026-10-11): full PRD built (Waves 1-3 complete), product renamed to "SafePayAI"
- `.claude/prd/` is now the source of truth for everything about this product — do not duplicate its content here. Start with `.claude/prd/README.md`, then `00-context-brief.md`, then `00-platform-prd.md` sec 12 for the 10 confirmed decisions (D1-D10, final, do not re-litigate).
- Product renamed "Made Whole" -> "SafePayAI" project-wide (user's explicit choice, overriding the agent-recommended name). Refund tool renamed `create_refund` -> `refund_capture`. Env-var convention is `PS_<SLUG>_*` everywhere except 3 documented exceptions (PAYPAL_CLIENT_ID/SECRET, MANDATE_HMAC_KEY[_PREVIOUS], INTERNAL_TICK_SECRET).
- Frontend stack: Next.js + shadcn/ui + Framer Motion + WebGL + Aceternity UI — user overrode my own risk recommendation (I'd argued WebGL/Aceternity clash with the trust/honesty positioning); landed on a compromise: heavy effects confined to the landing/hook moment only, money-path screens (mandate sign, approval, refund, audit) stay plain shadcn + light Framer Motion.
- 11 services fully specced (api-gateway, mandate, catalog, shopping-agent, checkout, paypal-adapter, tracking, resolution, triage-ai, audit, web), each with prd/spec/api/deployment/test-plan/sprint-tasks.md.
- UNRESOLVED, carried forward: official Devpost hackathon rules could not be fetched by any tool (403 everywhere) — judging weights, full submission artifact list, and the "one sponsor prize per project" rule are genuinely unconfirmed anywhere, not just by us. Check in a real logged-in browser before finalizing submission.
- Status: PRD/planning complete. Zero actual code/config exists yet (no git init, no OpenAPI files, no docker-compose, no migrations) — that's Wave 4 (scaffolding), not yet started. Full detail: `.claude/handoff/handoff-2026-10-11-0839.md`.
