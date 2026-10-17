import * as f from "../mocks/fixtures";
import type { MockOptions } from "./mock-api";

/** Answers for the buyer screens, built from the shared fixtures. */
export function buyerRoutes(): NonNullable<MockOptions["routes"]> {
  const id = f.IDS;
  return {
    "GET /bff/buyer-home": {
      body: { mandates: [f.mandate], latest_order: f.order, active_case: f.caseItem },
    },
    "GET /catalog/items": {
      body: {
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
          },
          {
            sku: "SKU-2",
            merchant_id: "mrc_atlas",
            category_id: "cables",
            title: "USB cable",
            description: "A cable",
            unit_price_minor: 900,
            currency: "USD",
            active: true,
          },
        ],
        limit: 100,
        offset: 0,
        has_more: false,
      },
    },
    "POST /agent/propose": { body: f.proposal },
    "POST /checkout/carts": { status: 201, body: f.cart },
    "POST /mandate/mandates/preview": () => ({
      body: { ...f.preview, nonce_expires_at: new Date(Date.now() + 120_000).toISOString() },
    }),
    "POST /mandate/mandates": { status: 201, body: f.mandate },
    [`GET /mandate/mandates/${id.mandate}`]: { body: f.mandate },
    [`GET /mandate/mandates/${id.mandate}/terms`]: {
      body: {
        mandate_id: id.mandate,
        mandate_hash: "abc123",
        terms_hash: "t1t1t1t1t1t1t1t1t1",
        mandate_status: "active",
        integrity: "OK",
        protection: f.terms.protection,
        revoke_effect: "FUTURE_ONLY",
        policy_version: "policy.v1",
        currency: "USD",
      },
    },
    [`POST /mandate/mandates/${id.mandate}/revoke`]: {
      body: {
        mandate_id: id.mandate,
        status: "revoked",
        revoked_at: f.ISO,
        released_reservations: 0,
        revoke_effect: "FUTURE_ONLY",
        earned_protection_unchanged: true,
        message_code: "FUTURE_PURCHASES_STOPPED",
      },
    },
  };
}
