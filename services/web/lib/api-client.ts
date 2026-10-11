/**
 * services/web/lib/api-client.ts
 *
 * Thin fetch wrapper for the api-gateway BFF. All calls go through the
 * same-origin `/api/*` path (Vercel rewrite -> PS_WEB_GATEWAY_INTERNAL_URL,
 * server-side only, see next.config.ts and deployment.md sec 1/4). The
 * client never talks to the Render origin directly (cookie would become
 * third-party and SameSite=Lax would break - R2 in prd.md sec 7).
 *
 * TODO Wave 5:
 *   - Generate request/response types from contracts/openapi/api-gateway.json
 *     (REQ-WB-058) instead of the placeholder `unknown` types below.
 *   - Add zod runtime validation per response, with graceful unknown-field
 *     tolerance (ADR-008 additive-only contract).
 *   - Wire real CSRF token handling (in-memory only, REQ-WB-011) and
 *     Idempotency-Key generation per mutating call (REQ-WB-051).
 *   - Wire cold-start / "waking up" retry-with-backoff for idempotent calls
 *     only (spec.md sec 12).
 *   - Replace every stub function body below with a real fetch() call.
 *
 * Nothing in this file performs authorization, pricing, or mandate
 * evaluation - it only shapes and forwards requests. The server is the sole
 * source of truth (spec.md sec 11).
 */

const API_BASE = process.env.NEXT_PUBLIC_PS_WEB_API_BASE ?? "/api";

// Placeholder shapes only - NOT the real contract. Replace with generated
// types in Wave 5.
export interface MandatePreview {
  mandate_id?: string;
  merchants: string[];
  max_total_minor: number;
  currency: string;
  intent: string;
  expiry: string;
  nonce: string;
}

export interface CartCheckResult {
  sku: string;
  status: "PASS" | "BLOCK" | "TIGHTEN";
  reason_code?: string;
}

export interface CartProposal {
  cart_id: string;
  lines: Array<{ sku: string; qty: number; unit_price_minor: number }>;
  total_minor: number;
  checks: CartCheckResult[];
  status: "OK" | "BLOCKED" | "NEEDS_BUYER_CONFIRMATION" | "REJECT_WITH_REASON";
  source?: "live" | "cached";
  badge?: string;
}

export interface ReceiptResponse {
  order_id: string;
  capture_id: string;
  items: Array<{ sku: string; qty: number }>;
  total_minor: number;
  mandate_id: string;
  checks: CartCheckResult[];
  protected_until_day: number;
  disclosures: string[];
}

/**
 * Internal helper - not exported. Wave 5 fills this in with the real fetch
 * call (credentials: "include" for the cookie, CSRF header, Idempotency-Key
 * on mutating verbs, cold-start retry-with-backoff).
 */
async function request<T>(_path: string, _init?: RequestInit): Promise<T> {
  // TODO Wave 5: implement. Throwing here keeps call sites honest that
  // nothing is wired yet, rather than silently returning fake data.
  throw new Error("api-client: not wired yet (Wave 4 skeleton, see TODO Wave 5)");
}

// --- Mandate (mandate service, via gateway) ---

export async function previewMandate(_input: {
  intent: string;
  maxTotalMinor: number;
  currency: string;
}): Promise<MandatePreview> {
  // TODO Wave 5: POST `${API_BASE}/mandates/preview`
  return request<MandatePreview>(`${API_BASE}/mandates/preview`);
}

export async function signMandate(_input: {
  nonce: string;
  screenTextHash: string;
}): Promise<{ mandate_id: string }> {
  // TODO Wave 5: POST `${API_BASE}/mandates`
  return request(`${API_BASE}/mandates`);
}

export async function revokeMandate(_mandateId: string): Promise<{
  released_reservations: number;
  message_code: string;
}> {
  // TODO Wave 5: POST `${API_BASE}/mandates/${_mandateId}/revoke`
  return request(`${API_BASE}/mandates/${_mandateId}/revoke`);
}

// --- Shopping agent (via gateway) ---

export async function proposeCart(_input: {
  mandateId: string;
  intentText: string;
}): Promise<CartProposal> {
  // TODO Wave 5: POST `${API_BASE}/agent/propose`
  return request<CartProposal>(`${API_BASE}/agent/propose`);
}

// --- Checkout (via gateway) ---

export async function createCart(_input: {
  mandateId: string;
  lines: Array<{ sku: string; qty: number }>;
}): Promise<CartProposal> {
  // TODO Wave 5: POST `${API_BASE}/carts`
  return request<CartProposal>(`${API_BASE}/carts`);
}

export async function confirmCart(_cartId: string): Promise<{ approve_url: string }> {
  // TODO Wave 5: POST `${API_BASE}/carts/${_cartId}/confirm`
  return request(`${API_BASE}/carts/${_cartId}/confirm`);
}

export async function completeReturn(_input: {
  state: string;
  token: string;
  payerId: string;
}): Promise<{ status: string; order_id?: string }> {
  // TODO Wave 5: POST `${API_BASE}/orders/return`
  return request(`${API_BASE}/orders/return`);
}

export async function getReceipt(_orderId: string): Promise<ReceiptResponse> {
  // TODO Wave 5: GET `${API_BASE}/orders/${_orderId}/receipt`
  return request<ReceiptResponse>(`${API_BASE}/orders/${_orderId}/receipt`);
}

// --- Resolution (cases/offers, via gateway) ---

export async function reportProblem(_input: {
  orderId: string;
  text: string;
}): Promise<{ case_id: string }> {
  // TODO Wave 5: POST `${API_BASE}/cases`
  return request(`${API_BASE}/cases`);
}

export async function getCase(_caseId: string): Promise<unknown> {
  // TODO Wave 5: GET `${API_BASE}/cases/${_caseId}`
  return request(`${API_BASE}/cases/${_caseId}`);
}

export async function respondToOffer(_input: {
  caseId: string;
  decision: "APPROVE" | "DECLINE";
}): Promise<unknown> {
  // TODO Wave 5: POST `${API_BASE}/cases/${_input.caseId}/offer-response`
  return request(`${API_BASE}/cases/${_input.caseId}/offer-response`);
}

// --- Merchant (orders/tracking/policy/review/audit/controls, via gateway) ---

export async function listMerchantOrders(): Promise<unknown[]> {
  // TODO Wave 5: GET `${API_BASE}/merchant/orders`
  return request(`${API_BASE}/merchant/orders`);
}

export async function addTracking(_input: {
  orderId: string;
  trackingNumber: string;
}): Promise<unknown> {
  // TODO Wave 5: POST `${API_BASE}/merchant/orders/${_input.orderId}/tracking`
  return request(`${API_BASE}/merchant/orders/${_input.orderId}/tracking`);
}

export async function getReviewQueue(): Promise<unknown[]> {
  // TODO Wave 5: GET `${API_BASE}/review/queue`
  return request(`${API_BASE}/review/queue`);
}

export async function getAuditEntries(): Promise<unknown[]> {
  // TODO Wave 5: GET `${API_BASE}/audit/entries`
  return request(`${API_BASE}/audit/entries`);
}

export async function verifyAuditChain(): Promise<{ ok: boolean; head_hash: string; epoch: number }> {
  // TODO Wave 5: GET `${API_BASE}/audit/verify`
  return request(`${API_BASE}/audit/verify`);
}

export async function getRefundsFrozen(): Promise<{ frozen: boolean }> {
  // TODO Wave 5: GET `${API_BASE}/controls/refunds-frozen`
  return request(`${API_BASE}/controls/refunds-frozen`);
}

// --- Warm-up (cold-start mitigation, spec.md sec 12) ---

export async function warmUp(): Promise<void> {
  // TODO Wave 5: fire-and-forget GET `${API_BASE}/healthz`-style endpoint on
  // landing-page load. Intentionally a no-op in Wave 4.
  return;
}
