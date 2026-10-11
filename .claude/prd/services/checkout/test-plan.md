# checkout: test plan

Labels V/VC/I. Stack: pytest + httpx ASGI client, Postgres (compose or ephemeral), fake adapter (in-process stub implementing the adapter DTO), WireMock-style fakes for catalog/mandate/shopping-agent, real PayPal sandbox only in the marked integration tier. Security IDs refer to `threat-model.md` s8 (T-ids).

## 1. Tiers
| Tier | Runs | Contents |
|---|---|---|
| U unit | every push | pure functions: totals, proposal_hash canonicalization, check combiner (tighten-only), state machine CAS, ticket mint, reason codes |
| C contract | every push | OpenAPI diff vs committed spec; response schema checks; consumer smoke tests against fakes; event JSON Schemas |
| I integration | PR + main (compose) | real Postgres, real mandate+catalog in-process, fake adapter; failure injection |
| S sandbox | manual + nightly before submission | real PayPal sandbox via real adapter; needs a real approval click for the approve step; US personal buyer (V: India buyer cannot pay USD) |
| E end-to-end hosted | 3 rehearsals before Nov 10 (I) | Render + Vercel + Neon, from the public URL |

## 2. Cases
P0 = must pass before demo.

### 2.1 Cart and checks
| ID | P | Case | Expected |
|---|---|---|---|
| CO-T01 | P0 | Valid cart inside mandate | 201 CHECKED; totals equal sum of catalog prices; checks listed |
| CO-T02 | P0 | Tampered amounts: body adds `amount_minor`, `total`, `currency`, `merchant_id` | 422 `FIELD_NOT_ALLOWED`; nothing persisted |
| CO-T03 | P0 | Agent-stated price differs from catalog | BLOCKED `PRICE_MISMATCH`; no order creatable |
| CO-T04 | P0 | Client modifies qty between cart and confirm; sends old `proposal_hash` | 409 `CART_CHANGED`; no PayPal call |
| CO-T05 | P0 | Catalog price changes between check and confirm | confirm re-prices; hash changes; 409 `CART_CHANGED` |
| CO-T06 | P0 | Each hard block (revoked, expired, merchant, over cap, unknown SKU, qty cap, currency) | BLOCKED with matching reason code; intent-fit NOT called (spy) |
| CO-T07 | P0 | Intent-fit returns PASS on a cart with a hard block (mock) | still BLOCKED |
| CO-T08 | P0 | Intent-fit timeout / bad JSON / 5xx | NEEDS_BUYER_CONFIRMATION; confirm without `confirm_intent_fit` -> 422 |
| CO-T09 | P0 | Mandate / catalog / evaluate unreachable or malformed | BLOCKED `MANDATE_UNAVAILABLE` / `CATALOG_UNAVAILABLE`; no order |
| CO-T10 | P0 | Cumulative cap: second cart exceeds remaining cap | BLOCKED `OVER_CAP`; `committed_minor` counts in-flight orders |
| CO-T11 | P0 | IDOR: buyer B uses buyer A's cart/mandate/order | 404 on every endpoint (enumerated) |
| CO-T12 | P1 | Property test: combiner never returns allowed when any block present | passes for generated inputs |

### 2.2 Order creation, idempotency, replay
| ID | P | Case | Expected |
|---|---|---|---|
| CO-T20 | P0 | Create order: row CREATING with request_id exists BEFORE adapter call (adapter fake asserts DB state) | R4 holds |
| CO-T21 | P0 | `custom_id == mandate_id`, `invoice_id == order_id` in adapter call | asserted |
| CO-T22 | P0 | Replay `POST /confirm` same `Idempotency-Key`+body | same response; one order; one adapter create |
| CO-T23 | P0 | Same key, different body | 422 `IDEMPOTENCY_KEY_REUSED` |
| CO-T24 | P0 | Two concurrent confirms for one cart | exactly one order (unique cart_id); other gets the same order or 409 |
| CO-T25 | P0 | Replay: adapter timeout on create then retry | same `create_request_id` reused; single PayPal order (S tier: V replay returns SAME order) |
| CO-T26 | P0 | Authorization ticket tampered (amount changed) at adapter fake | `AUTHORIZATION_MISMATCH`; order CREATE_FAILED; no PayPal order |
| CO-T27 | P1 | Duplicate `invoice_id` response from adapter | CREATE_FAILED; no retry with new id |

### 2.3 Return-URL state forgery and binding (return path is UNTESTED against real PayPal, I)
| ID | P | Case | Expected |
|---|---|---|---|
| CO-T30 | P0 | Forged/random `state` | 400 `STATE_INVALID`; no state change |
| CO-T31 | P0 | Valid state, wrong `token` (another PayPal order id) | 400 `TOKEN_MISMATCH`; no capture; alert log |
| CO-T32 | P0 | Valid state used by a different buyer session | 403 `BUYER_MISMATCH`; state not consumed |
| CO-T33 | P0 | No principal (cookie lost) | 401 `SIGN_IN_REQUIRED`; state unconsumed; zero adapter capture calls |
| CO-T34 | P0 | Expired state | 400; order stays AWAITING_APPROVAL then EXPIRED by reconcile |
| CO-T35 | P0 | Replay of consumed state / page refresh | 200 existing result; zero second capture |
| CO-T36 | P0 | Attacker pays own order and tricks victim into return with attacker's token | `TOKEN_MISMATCH` against victim's stored order |
| CO-T37 | P0 | Return before buyer approved (status PAYER_ACTION_REQUIRED) | 409 `NOT_APPROVED`; state reusable |
| CO-T38 | P0 | Order amount/currency/custom_id/invoice_id mutated in PayPal response | `ORDER_MISMATCH`; no capture; `order.capture_failed` |
| CO-T39 | P1 | `Referrer-Policy` and log redaction of `token`,`state`,`PayerID` | headers present; grep logs clean |
| CO-T3A | P0 | S tier: real redirect to our server (tunnel, then Render+Vercel) | recorded result; if it fails, manual `/orders/{id}/capture` path proven |

### 2.4 Capture, replay, revoke race
| ID | P | Case | Expected |
|---|---|---|---|
| CO-T40 | P0 | Happy path S tier: PAYER_ACTION_REQUIRED -> approve click -> APPROVED -> capture 201 COMPLETED | CAPTURED; captures row; receipt; `order.captured` once (V sequence) |
| CO-T41 | P0 | Capture replay: call `/orders/{id}/capture` 5x concurrently | one capture row; one `order.captured`; others return existing |
| CO-T42 | P0 | Revoke race A: revoke committed before return | CANCELLED_REVOKED; zero adapter capture calls; `order.capture_failed` MANDATE_REVOKED |
| CO-T43 | P0 | Revoke race B: revoke lands between pre-capture check and capture call (fake adapter delays) | document outcome: capture may proceed because check passed before revoke commit; test asserts no capture starts AFTER a committed revoke is observed on the re-check. Residual window stated honestly in the receipt/docs (I) |
| CO-T44 | P0 | `mandate.revoked` event lost/delayed | still blocked via sync check |
| CO-T45 | P0 | Mandate service down at capture | no capture; order stays APPROVED/ retriable; fail closed |
| CO-T46 | P0 | Revoke after capture | order unaffected (stop wins for FUTURE spend only; I pending PM) |
| CO-T47 | P0 | custom_id / invoice_id present on capture read-back (S tier) | equal mandate_id / order_id (V) |

### 2.5 PENDING, failed, unknown capture
| ID | P | Case | Expected |
|---|---|---|---|
| CO-T50 | P1 | Adapter returns capture PENDING (fake; UNVERIFIED in sandbox) | CAPTURE_PENDING; no `order.captured`; no "Protected"; poll to COMPLETED -> CAPTURED |
| CO-T51 | P1 | PENDING resolves to DECLINED/FAILED | CAPTURE_FAILED; event emitted |
| CO-T52 | P1 | PENDING never resolves | remains CAPTURE_PENDING; reviewer-visible; refunds blocked (resolution reads status) |
| CO-T53 | P0 | Capture 4xx/422 definite failure | CAPTURE_FAILED with code; `order.capture_failed` |
| CO-T54 | P0 | Capture timeout then reconcile: PayPal says COMPLETED | adopts capture_id, no second capture call (spy) |
| CO-T55 | P0 | Capture timeout then PayPal says APPROVED | one recapture with SAME `capture_request_id` |
| CO-T56 | P0 | 409 on capture (concurrent same id) | UNKNOWN -> reconcile, no new id |
| CO-T57 | P0 | `MONEY_ENABLED=false` at adapter | CAPTURE_FAILED `MONEY_DISABLED`; no retry loop |
| CO-T58 | P1 | Kill process mid-CAPTURING; restart; reconcile | ends in a consistent terminal state; no double capture |

### 2.6 Receipt and events
| ID | P | Case | Expected |
|---|---|---|---|
| CO-T60 | P0 | Receipt fields present: checks[], intent_fit advisory:true, mandate_hash, audit.event_id, remaining_cap_minor, protection label | schema test |
| CO-T61 | P0 | Receipt immutable; not available before CAPTURED | 409 `RECEIPT_NOT_READY` |
| CO-T62 | P0 | `remaining_cap_minor` equals cap minus committed | arithmetic test |
| CO-T63 | P0 | Receipt never says "PayPal protected/backed" | string lint on templates and fixtures |
| CO-T64 | P0 | Events: schema-valid, outbox written in same txn as state change; consumer dedupe on duplicate delivery | passes |
| CO-T65 | P1 | Audit down | capture succeeds; outbox retries |

### 2.7 Security and hygiene
| ID | P | Case | Maps |
|---|---|---|---|
| CO-T70 | P0 | Missing/expired/wrong-aud/alg=none JWT -> 401; role mismatch -> 403 | T19 |
| CO-T71 | P0 | Env manifest: no PayPal/LLM/mandate-HMAC vars in checkout | T14/forbidden vars |
| CO-T72 | P0 | gitleaks full history; no secrets in fixtures/logs | T13 |
| CO-T73 | P1 | No stack traces or internal URLs in errors | T21 |
| CO-T74 | P0 | Client-supplied money fields rejected on all endpoints | T22 |
| CO-T75 | P1 | return_url/cancel_url built only from config; no user URL accepted | T12 |

## 3. CI side-by-side
Two jobs run in parallel on every PR; both must be green to merge:
- Job 1 `profile-b`: `core` + `ai`/`paypal` stubs mounted in-process (`INPROCESS_TRANSPORT=true`).
- Job 2 `profile-a`: `docker compose up` with separate containers, HTTP between services.
- The same test suite (U, C, I tiers and the CO-T20..T75 integration cases) runs against both; results compared; any case passing in one and failing in the other fails CI (catches in-process shortcuts, missing JWT audience checks, timeout differences).
- Sandbox tier S runs outside the PR gate (needs secrets and a human click); results recorded in the repo as dated notes.

## 4. Test data and tooling
- Seeded catalog and sample mandates via `scripts/seed`; fixtures label sandbox values; no real credentials in fixtures.
- Fake adapter implements: success, definite 4xx, timeout, 409/UNKNOWN, PENDING, mismatching order payload, delayed responses.
- Clock injected into checkout (TTL tests do not sleep).
- Coverage and mutation thresholds: not set (no invented numbers); critical modules (combiner, state machine, return handler) require explicit tests listed above.

## 5. Definition of done (service)
- [ ] All P0 cases pass in CI on both profiles.
- [ ] S-tier happy path (CO-T40, T47) recorded in sandbox with real approve click; result noted.
- [ ] Return URL tested through the hosted Render+Vercel layout (CO-T3A) OR the manual capture fallback is proven and documented as the demo path.
- [ ] PENDING handled in code and tests; docs say "unverified in sandbox" unless observed.
- [ ] OpenAPI and event schemas committed; CI diff green.
- [ ] No secrets; gitleaks green on history; env manifest test green.
- [ ] Zero mismatched/post-revoke/double captures in the test run (properties asserted).
- [ ] Receipt shows checks, advisory label, mandate hash, audit event, remaining cap, demo-window label.
- [ ] Reconcile job runs repeatedly without side effects.
- [ ] README/service doc states sandbox only, no PayPal-protected claim, conflicts C1-C13 resolved or acknowledged.
- [ ] Rollback rehearsed once (redeploy previous SHA + reconcile).
