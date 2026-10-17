/**
 * Response bodies in the shapes the deployed gateway returns. Test-only;
 * app code never imports from tests/.
 */
export const IDS = {
  buyer: "11111111-1111-4111-8111-111111111111",
  mandate: "22222222-2222-4222-8222-222222222222",
  cart: "33333333-3333-4333-8333-333333333333",
  order: "44444444-4444-4444-8444-444444444444",
  case: "55555555-5555-4555-8555-555555555555",
  offer: "66666666-6666-4666-8666-666666666666",
  shipment: "77777777-7777-4777-8777-777777777777",
} as const;

export const ISO = "2026-10-17T12:00:00Z";

export const terms = {
  currency: "USD",
  max_total_minor: 50000,
  max_qty_per_line: 5,
  merchant_allowlist: [{ merchant_id: "mrc_northwind", display_name: "Northwind Audio" }],
  intent_text: "Headphones under $150",
  expires_at: "2026-10-24T12:00:00Z",
  protection: { kinds_covered: ["LATE", "LOST"], max_refund_minor: 5000, deliver_by_days: 7 },
  policy_version: "policy.v1",
  revoke_effect: "FUTURE_ONLY",
};

export const principal = {
  actor_type: "buyer",
  actor_id: IDS.buyer,
  role: "buyer",
  display_name: "demo-buyer-ab12cd34",
};

export const session = { principal, expires_at: "2026-10-18T12:00:00Z" };

export const me = {
  actor_type: "buyer",
  actor_id: IDS.buyer,
  role: "buyer",
  auth_method: "session",
  display_name: "demo-buyer-ab12cd34",
  merchant_id: null,
  session_expires_at: "2026-10-18T12:00:00Z",
};

export const csrf = (purpose = "general") => ({
  csrf_token: `csrf-${purpose}-${Math.random().toString(36).slice(2)}`,
  purpose,
  expires_at: "2026-10-17T13:00:00Z",
});

export const mandate = {
  mandate_id: IDS.mandate,
  buyer_id: IDS.buyer,
  status: "active",
  integrity: "OK",
  schema: "mandate.v1",
  render_version: "render.v1",
  policy_version: "policy.v1",
  currency: "USD",
  max_total_minor: 50000,
  max_qty_per_line: 5,
  merchant_allowlist: terms.merchant_allowlist,
  intent_text: terms.intent_text,
  expires_at: terms.expires_at,
  protection: terms.protection,
  revoke_effect: "FUTURE_ONLY",
  mandate_hash: "abc123",
  screen_text_hash: "def456",
  hmac_key_id: "k1",
  spent_minor: 34000,
  reserved_minor: 0,
  remaining_minor: 16000,
  created_at: ISO,
};

export const preview = {
  normalized_terms: terms,
  screen_text: "You authorise purchases up to $500.00.",
  screen_text_hash: "def456",
  render_version: "render.v1",
  policy_version: "policy.v1",
  nonce: "nonce-abcdefghijklmnop",
  nonce_expires_at: "2026-10-17T12:02:00Z",
};

export const order = {
  order_id: IDS.order,
  cart_id: IDS.cart,
  buyer_id: IDS.buyer,
  mandate_id: IDS.mandate,
  status: "AWAITING_APPROVAL",
  total_minor: 4820,
  currency: "USD",
  paypal_order_id: "PP-1",
  approve_url: "https://www.sandbox.paypal.com/checkoutnow?token=PP-1",
  failure_code: null,
  created_at: ISO,
  updated_at: ISO,
  capture_id: null,
  capture_status: null,
  mandate_reservation_id: null,
  item_titles: ["Wired earbuds"],
};

export const capturedOrder = { ...order, status: "CAPTURED", capture_id: "CAP-1" };

export const cart = {
  cart_id: IDS.cart,
  status: "CHECKED",
  currency: "USD",
  lines: [
    { sku: "SKU-1", qty: 1, unit_minor: 4820, line_minor: 4820, merchant_id: "mrc_northwind" },
  ],
  total_minor: 4820,
  remaining_cap_minor_after: 16000,
  proposal_hash: "hash-1",
  checks: [{ name: "mandate_evaluate", result: "PASS", reason_code: null, source: "mandate" }],
  intent_fit: null,
  expires_at: ISO,
};

export const receipt = {
  order_id: IDS.order,
  paypal_order_id: "PP-1",
  capture_id: "CAP-1",
  status: "CAPTURED",
  amount_minor: 4820,
  amount_major: "48.20",
  currency: "USD",
  lines: [
    {
      sku: "SKU-1",
      qty: 1,
      unit_minor: 4820,
      unit_major: "48.20",
      line_minor: 4820,
      line_major: "48.20",
      merchant_id: "mrc_northwind",
    },
  ],
  checks: [
    {
      name: "mandate_evaluate",
      result: "PASS",
      reason_code: null,
      source: "mandate",
      detail: null,
    },
  ],
  intent_fit: null,
  mandate: { mandate_id: IDS.mandate, mandate_hash: "abc123" },
  audit: { event_id: IDS.order, seq: null },
  remaining_cap_minor: 11180,
  protection: { window_days: 7, protected_until_day: 7, label: "Demo window, not PayPal's" },
  disclosures: [
    "Sandbox only",
    "Demo protection window is illustrative",
    "Merchant-funded via PayPal refund",
  ],
};

export const proposal = {
  proposal_id: "prop-1",
  status: "OK",
  source: "live",
  lines: [{ sku: "SKU-1", quantity: 1, display_title: "Wired earbuds" }],
  rationale: "Closest match inside the mandate.",
  confidence: 0.82,
  no_match_reason: null,
  model: null,
  latency_ms: 900,
  badge: null,
  recorded_model: null,
  trace_id: "trace-1",
};

export const caseItem = {
  case_id: IDS.case,
  order_id: IDS.order,
  state: "OFFERED",
  kind: "LATE",
  origin: "DETECTOR",
  opened_at: ISO,
};

export const offer = {
  offer_id: IDS.offer,
  action: "REFUND",
  amount_minor: 4820,
  currency: "USD",
  tier: "CONFIRM",
  status: "ACTIVE",
  proposal_hash: "offer-hash-1",
  expires_at: "",
};

export const tracking = {
  order_id: IDS.order,
  sim_now: ISO,
  shipments: [
    { id: IDS.shipment, status: "IN_TRANSIT", active: true, promised_at_sim: ISO, anomaly: null },
  ],
  events: [
    {
      event_id: `${IDS.shipment}-1`,
      shipment_id: IDS.shipment,
      status: "IN_TRANSIT",
      occurred_at_sim: ISO,
      note_code: null,
    },
  ],
  consistency: {
    delivered: false,
    delivered_at_sim: null,
    late_detected: false,
    lost_detected: false,
  },
  simulated: true,
  carrier_label: "SIMULATED CARRIER",
};

export const auditRow = {
  seq: 12,
  recorded_at: ISO,
  event_type: "order.captured",
  actor_type: "buyer",
  actor_id: IDS.buyer,
  auth_method: "session",
  request_id: "req-1",
  mandate_id: IDS.mandate,
  order_id: IDS.order,
  case_id: null,
  summary: "Order Captured",
  row_hash_short: "aaaabbbb",
  prev_hash_short: "ccccdddd",
};

export const refundsFrozen = {
  refunds_frozen: true,
  reason: "demo reset",
  set_by: "operator",
  set_at: null,
  epoch: 1,
  adapter_mirror: "PENDING",
  readable: true,
};
