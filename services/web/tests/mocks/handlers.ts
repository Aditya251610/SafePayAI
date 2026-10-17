import { http, HttpResponse, type HttpHandler } from "msw";
import * as f from "./fixtures";

export const TEST_BASE = "http://gateway.test/api";

export interface RecordedCall {
  method: string;
  path: string;
  search: string;
  headers: Record<string, string>;
  body: unknown;
}

export const calls: RecordedCall[] = [];

export function resetCalls(): void {
  calls.length = 0;
}

export function callsTo(method: string, path: string): RecordedCall[] {
  return calls.filter((c) => c.method === method && c.path === path);
}

async function record(request: Request): Promise<void> {
  const url = new URL(request.url);
  let body: unknown;
  const text = await request.clone().text();
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  calls.push({
    method: request.method,
    path: url.pathname.replace(/^\/api/, ""),
    search: url.search,
    headers: Object.fromEntries(request.headers.entries()),
    body,
  });
}

type Method = "get" | "post" | "put";

/** Override helper for tests: same recording as the defaults, custom resolver. */
export function recorded(
  method: Method,
  path: string,
  resolver: () => Response | Promise<Response>,
): HttpHandler {
  return http[method](`${TEST_BASE}${path}`, async ({ request }) => {
    await record(request);
    return resolver();
  });
}

function route(method: Method, path: string, status: number, body: unknown): HttpHandler {
  return http[method](`${TEST_BASE}${path}`, async ({ request }) => {
    await record(request);
    if (body === undefined) return new HttpResponse(null, { status });
    return HttpResponse.json(body as Record<string, unknown>, { status });
  });
}

/** Default happy-path handlers for every route the client can call. */
export function defaultHandlers(): HttpHandler[] {
  const id = f.IDS;
  return [
    http.get(`${TEST_BASE}/auth/csrf`, async ({ request }) => {
      await record(request);
      const purpose = new URL(request.url).searchParams.get("purpose") ?? "general";
      return HttpResponse.json(f.csrf(purpose));
    }),
    route("post", "/auth/demo-session", 201, f.session),
    route("post", "/auth/login", 200, f.session),
    route("post", "/auth/logout", 204, undefined),
    route("get", "/auth/me", 200, f.me),

    route("post", "/mandate/mandates/preview", 200, f.preview),
    route("post", "/mandate/mandates", 201, f.mandate),
    route("get", `/mandate/mandates/${id.mandate}`, 200, f.mandate),
    route("get", `/mandate/mandates/${id.mandate}/terms`, 200, {
      mandate_id: id.mandate,
      mandate_hash: "abc123",
      terms_hash: "t1",
      mandate_status: "active",
      integrity: "OK",
      protection: f.terms.protection,
      revoke_effect: "FUTURE_ONLY",
      policy_version: "policy.v1",
      currency: "USD",
    }),
    route("post", `/mandate/mandates/${id.mandate}/revoke`, 200, {
      mandate_id: id.mandate,
      status: "revoked",
      revoked_at: f.ISO,
      released_reservations: 0,
      revoke_effect: "FUTURE_ONLY",
      earned_protection_unchanged: true,
      message_code: "FUTURE_PURCHASES_STOPPED",
    }),

    route("get", "/catalog/items", 200, {
      catalog_version: 1,
      items: [
        {
          sku: "SKU-1",
          merchant_id: "mrc_northwind",
          category_id: "audio",
          title: "Wired earbuds",
          description: "Plain earbuds",
          unit_price_minor: 4820,
          currency: "USD",
          active: true,
          text_trust: "untrusted",
          label: "SIMULATED",
        },
      ],
      limit: 50,
      offset: 0,
      has_more: false,
    }),
    route("get", "/catalog/items/SKU-1", 200, {
      sku: "SKU-1",
      merchant_id: "mrc_northwind",
      category_id: "audio",
      title: "Wired earbuds",
      description: "Plain earbuds",
      unit_price_minor: 4820,
      currency: "USD",
      active: true,
      catalog_version: 1,
    }),

    route("post", "/agent/propose", 200, f.proposal),

    route("post", "/checkout/carts", 201, f.cart),
    route("post", `/checkout/carts/${id.cart}/confirm`, 201, {
      order_id: id.order,
      status: "AWAITING_APPROVAL",
      approve_url: f.order.approve_url,
      total_minor: 4820,
      currency: "USD",
      expires_at: f.ISO,
    }),
    route("post", `/checkout/orders/${id.order}/capture`, 200, f.capturedOrder),
    route("get", `/checkout/orders/${id.order}`, 200, f.order),
    route("get", `/checkout/orders/${id.order}/receipt`, 200, f.receipt),
    route("get", "/checkout/orders", 200, { items: [f.order] }),
    route("post", "/checkout/orders/return", 200, {
      order_id: id.order,
      status: "CAPTURED",
      receipt_url: `/orders/${id.order}/receipt`,
      message_code: "CAPTURED",
    }),
    route("post", "/checkout/orders/cancel", 200, {
      order_id: id.order,
      status: "CANCELLED_BUYER",
    }),

    route("post", "/tracking/shipments", 201, {
      id: id.shipment,
      order_id: id.order,
      status: "LABEL_CREATED",
      promised_at_sim: f.ISO,
      paypal_sync: "ADDED",
      paypal_tracker_id: "TRK-1",
      simulated: true,
      carrier_label: "SIMULATED CARRIER",
    }),
    route("get", `/tracking/shipments/${id.order}`, 200, f.tracking),
    route("get", "/tracking/demo/clock", 200, { sim_now: f.ISO }),
    route("post", "/tracking/demo/clock/advance", 200, {
      from_sim: f.ISO,
      to_sim: "2026-10-18T12:00:00Z",
      version: 2,
      tick: { applied: 1, detected: 0, skipped_lease: false },
    }),
    route("post", "/tracking/demo/clock/reset", 200, { offset_seconds: 0 }),
    route("post", `/tracking/demo/shipments/${id.shipment}/force`, 200, {
      id: id.shipment,
      status: "LOST",
      source: "FORCE",
      tick: { applied: 1, detected: 1, skipped_lease: false },
    }),

    route("post", "/resolution/cases/report", 201, {
      case_id: id.case,
      state: "OFFERED",
      kind: "LATE",
      origin: "BUYER_REPORT",
      reasons: [{ code: "IN_TERMS", text: null }],
      offer: f.offer,
      protection: {},
    }),
    route("get", `/resolution/cases/${id.case}`, 200, {
      case_id: id.case,
      order_id: id.order,
      state: "OFFERED",
      version: 2,
      kind: "LATE",
      origin: "DETECTOR",
      opened_at: f.ISO,
      window_hold: false,
      timeline: [],
      decision: null,
      offer: null,
      refund: null,
      queued_reason: null,
    }),
    route("get", "/resolution/cases", 200, { items: [f.caseItem] }),
    route("get", "/resolution/review/queue", 200, {
      items: [
        {
          case_id: id.case,
          kind: "LATE",
          reason_codes: ["POLICY_CAP"],
          entered_at: f.ISO,
          age_s: 60,
          sla_target_s: null,
          sla_state: "NO_TARGET",
          brief: "Over the policy cap.",
        },
      ],
    }),
    route("post", `/resolution/offers/${id.offer}/accept`, 200, {
      case_id: id.case,
      state: "REFUNDING",
      execution: "IN_PROGRESS",
      refund: { status: "REQUESTED", paypal_refund_id: null },
    }),
    route("post", `/resolution/offers/${id.offer}/decline`, 200, { state: "DECLINED" }),
    route("get", "/resolution/approvals/tok-1", 200, {
      case_id: id.case,
      action: "REFUND",
      amount_minor: 6000,
      currency: "USD",
      summary: "Refund $60.00",
      expires_at: f.ISO,
      proposal_hash: "offer-hash-2",
    }),
    route("post", "/resolution/approvals/tok-1/consent", 200, {
      case_id: id.case,
      state: "REFUNDING",
      execution: "IN_PROGRESS",
    }),
    route("post", `/resolution/cases/${id.case}/merchant-action`, 200, {
      case_id: id.case,
      state: "OFFERED",
      offer_id: id.offer,
      supersedes: null,
    }),
    route("get", "/resolution/controls/refunds-frozen", 200, f.refundsFrozen),

    route("get", "/audit/entries", 200, { rows: [f.auditRow], lastRow: 1, head_seq: 12 }),
    route("get", "/audit/verify", 200, {
      ok: true,
      chain_id: "main",
      checked: 12,
      head_seq: 12,
      head_hash: "h",
      algorithm: "sha256",
      duration_ms: 3,
      anchor: null,
    }),

    route("get", "/ops/status", 200, {
      demo_mode: true,
      money_routes_enabled: true,
      refunds_frozen: "true",
      build_id: "test",
    }),
    route("post", "/ops/freeze", 200, { ...f.refundsFrozen, refunds_frozen: false }),

    route("get", "/bff/buyer-home", 200, {
      mandates: [f.mandate],
      latest_order: f.order,
      active_case: f.caseItem,
    }),
    route("get", `/bff/orders/${id.order}`, 200, {
      order: f.order,
      shipment: f.tracking,
      case: f.caseItem,
      audit_verified: true,
    }),
    route("get", "/bff/merchant-queue", 200, { cases: [f.caseItem], tracking_pending: 3 }),
  ];
}
