import { describe, expect, it } from "vitest";
import { IDS, terms } from "../../mocks/fixtures";
import { TEST_BASE, calls, callsTo } from "../../mocks/handlers";
import { ApiError, InvalidIdError, createApi, createClient } from "@/lib/api";

const api = createApi(createClient({ baseUrl: TEST_BASE, sleep: () => Promise.resolve() }));

function last() {
  const c = calls[calls.length - 1];
  if (!c) throw new Error("no call recorded");
  return c;
}

describe("auth", () => {
  it("demoSession posts without CSRF", async () => {
    const r = await api.auth.demoSession();
    expect(r.principal.role).toBe("buyer");
    expect(callsTo("GET", "/auth/csrf")).toHaveLength(0);
  });
  it("login posts credentials without CSRF", async () => {
    await api.auth.login({ handle: "operator", password: "pw" });
    expect(last().body).toEqual({ handle: "operator", password: "pw" });
    expect(callsTo("GET", "/auth/csrf")).toHaveLength(0);
  });
  it("login rejects empty credentials locally", async () => {
    await expect(api.auth.login({ handle: "", password: "" })).rejects.toBeInstanceOf(Error);
    expect(calls).toHaveLength(0);
  });
  it("logout resolves on 204 without CSRF", async () => {
    await expect(api.auth.logout()).resolves.toBeUndefined();
    expect(callsTo("GET", "/auth/csrf")).toHaveLength(0);
  });
  it("me reads the principal", async () => {
    expect((await api.auth.me()).role).toBe("buyer");
  });
});

describe("mandate", () => {
  it("preview sends terms with CSRF and no idempotency key", async () => {
    const r = await api.mandate.preview(terms as never);
    expect(r.nonce).toBeTruthy();
    const p = callsTo("POST", "/mandate/mandates/preview")[0];
    expect((p?.body as { terms: unknown }).terms).toBeTruthy();
    expect(p?.headers["x-csrf-token"]).toBeTruthy();
    expect(p?.headers["idempotency-key"]).toBeUndefined();
  });
  it("preview validates terms locally (empty allowlist)", async () => {
    const bad = { ...terms, merchant_allowlist: [] };
    const err = (await api.mandate.preview(bad as never).catch((e: unknown) => e)) as ApiError;
    expect(err.code).toBe("VALIDATION_ERROR");
    expect(err.fields.some((f) => f.field.includes("merchant_allowlist"))).toBe(true);
    expect(calls).toHaveLength(0);
  });
  it("sign sends nonce and hash with an idempotency key", async () => {
    const prev = (await api.mandate.preview(terms as never)).normalized_terms;
    await api.mandate.sign({ terms: prev, screen_text_hash: "def456", nonce: "n" });
    const p = callsTo("POST", "/mandate/mandates")[0];
    expect(p?.headers["idempotency-key"]).toBeTruthy();
    expect(p?.body).toMatchObject({ screen_text_hash: "def456", nonce: "n" });
  });
  it("get and terms read by uuid", async () => {
    expect((await api.mandate.get(IDS.mandate)).remaining_minor).toBe(16000);
    expect((await api.mandate.terms(IDS.mandate)).terms_hash).toBe("t1");
  });
  it("get rejects a non-UUID without calling the gateway", async () => {
    await expect(api.mandate.get("preview")).rejects.toBeInstanceOf(InvalidIdError);
    expect(calls).toHaveLength(0);
  });
  it("revoke sends the reason code the service requires", async () => {
    const r = await api.mandate.revoke(IDS.mandate);
    expect(r.status).toBe("revoked");
    expect(callsTo("POST", `/mandate/mandates/${IDS.mandate}/revoke`)[0]?.body).toEqual({
      reason_code: "BUYER_REQUEST",
    });
  });
});

describe("catalog", () => {
  it("lists items with query params", async () => {
    const r = await api.catalog.items({ merchant_id: "mrc_northwind", limit: 10 });
    expect(r.items[0]?.sku).toBe("SKU-1");
    expect(callsTo("GET", "/catalog/items")[0]?.search).toBe("?merchant_id=mrc_northwind&limit=10");
  });
  it("reads one item by sku", async () => {
    expect((await api.catalog.item("SKU-1")).catalog_version).toBe(1);
  });
});

describe("agent", () => {
  it("propose sends an idempotency key", async () => {
    const r = await api.agent.propose({
      mandate_id: IDS.mandate,
      mode: "intent",
      intent_text: "earbuds",
    });
    expect(r.status).toBe("OK");
    expect(callsTo("POST", "/agent/propose")[0]?.headers["idempotency-key"]).toBeTruthy();
  });
  it("propose rejects form mode without a form", async () => {
    await expect(
      api.agent.propose({ mandate_id: IDS.mandate, mode: "form" }),
    ).rejects.toMatchObject({
      code: "VALIDATION_ERROR",
    });
  });
  it("propose rejects intent mode without text", async () => {
    await expect(
      api.agent.propose({ mandate_id: IDS.mandate, mode: "intent", intent_text: "  " }),
    ).rejects.toMatchObject({ code: "VALIDATION_ERROR" });
  });
});

describe("checkout", () => {
  it("createCart", async () => {
    const r = await api.checkout.createCart({
      mandate_id: IDS.mandate,
      lines: [{ sku: "SKU-1", qty: 1 }],
    });
    expect(r.status).toBe("CHECKED");
    expect(callsTo("POST", "/checkout/carts")[0]?.headers["idempotency-key"]).toBeTruthy();
  });
  it("confirmCart sends the proposal hash", async () => {
    const r = await api.checkout.confirmCart(IDS.cart, { proposal_hash: "hash-1" });
    expect(r.order_id).toBe(IDS.order);
    expect(callsTo("POST", `/checkout/carts/${IDS.cart}/confirm`)[0]?.body).toEqual({
      proposal_hash: "hash-1",
    });
  });
  it("capture posts an empty body", async () => {
    const r = await api.checkout.capture(IDS.order);
    expect(r.status).toBe("CAPTURED");
    expect(callsTo("POST", `/checkout/orders/${IDS.order}/capture`)[0]?.body).toEqual({});
  });
  it("order, receipt and orders", async () => {
    expect((await api.checkout.order(IDS.order)).status).toBe("AWAITING_APPROVAL");
    expect((await api.checkout.receipt(IDS.order)).disclosures).toContain(
      "Merchant-funded via PayPal refund",
    );
    expect((await api.checkout.orders({ limit: 5 })).items).toHaveLength(1);
    expect(callsTo("GET", "/checkout/orders")[0]?.search).toBe("?limit=5");
  });
  it("orders validates mandateId", async () => {
    await expect(api.checkout.orders({ mandateId: "nope" })).rejects.toBeInstanceOf(InvalidIdError);
  });
  it("completeReturn and cancelReturn", async () => {
    const r = await api.checkout.completeReturn({ state: "s", token: "t", payer_id: "p" });
    expect(r.message_code).toBe("CAPTURED");
    expect((await api.checkout.cancelReturn("s")).status).toBe("CANCELLED_BUYER");
  });
});

describe("tracking", () => {
  it("createShipment", async () => {
    const r = await api.tracking.createShipment({
      order_id: IDS.order,
      tracking_number: "T1",
      carrier_name: "Sim",
    });
    expect(r.status).toBe("LABEL_CREATED");
  });
  it("forOrder", async () => {
    expect((await api.tracking.forOrder(IDS.order)).shipments).toHaveLength(1);
  });
  it("demo clock routes", async () => {
    expect((await api.tracking.demoClock()).sim_now).toBeTruthy();
    expect(
      (await api.tracking.advanceClock({ delta_seconds: 86400, reason: "demo" })).version,
    ).toBe(2);
    expect((await api.tracking.resetClock()).offset_seconds).toBe(0);
  });
  it("forceShipment sends to_status and reason", async () => {
    const r = await api.tracking.forceShipment(IDS.shipment, { to_status: "LOST", reason: "demo" });
    expect(r.status).toBe("LOST");
    expect(callsTo("POST", `/tracking/demo/shipments/${IDS.shipment}/force`)[0]?.body).toEqual({
      to_status: "LOST",
      reason: "demo",
    });
  });
});

describe("resolution", () => {
  it("report", async () => {
    const r = await api.resolution.report({ order_id: IDS.order, text: "never arrived" });
    expect(r.offer?.proposal_hash).toBe("offer-hash-1");
  });
  it("report rejects empty text locally", async () => {
    await expect(api.resolution.report({ order_id: IDS.order, text: " " })).rejects.toMatchObject({
      code: "VALIDATION_ERROR",
    });
  });
  it("case, cases, reviewQueue", async () => {
    expect((await api.resolution.case(IDS.case)).state).toBe("OFFERED");
    expect((await api.resolution.cases()).items).toHaveLength(1);
    expect((await api.resolution.reviewQueue()).items[0]?.sla_state).toBe("NO_TARGET");
  });
  it("acceptOffer sends the proposal hash", async () => {
    const r = await api.resolution.acceptOffer(IDS.offer, "offer-hash-1");
    expect(r.execution).toBe("IN_PROGRESS");
    expect(callsTo("POST", `/resolution/offers/${IDS.offer}/accept`)[0]?.body).toEqual({
      proposal_hash: "offer-hash-1",
    });
  });
  it("declineOffer sends the reason enum", async () => {
    expect((await api.resolution.declineOffer(IDS.offer, "WANT_HUMAN")).state).toBe("DECLINED");
  });
  it("approvalPreview and consent", async () => {
    expect((await api.resolution.approvalPreview("tok-1")).amount_minor).toBe(6000);
    await api.resolution.consent("tok-1", { proposalHash: "offer-hash-2", csrfNonce: "n" });
    expect(callsTo("POST", "/resolution/approvals/tok-1/consent")[0]?.body).toEqual({
      proposal_hash: "offer-hash-2",
      csrf_nonce: "n",
    });
  });
  it("merchantAction", async () => {
    expect((await api.resolution.merchantAction(IDS.case, "OVERRIDE_OFFER")).offer_id).toBe(
      IDS.offer,
    );
  });
  it("refundsFrozen", async () => {
    expect((await api.resolution.refundsFrozen()).refunds_frozen).toBe(true);
  });
});

describe("audit", () => {
  it("entries pages with after_seq and a limit", async () => {
    const r = await api.audit.entries({ limit: 25, after_seq: 10 });
    expect(r.rows[0]?.seq).toBe(12);
    expect(callsTo("GET", "/audit/entries")[0]?.search).toBe("?endRow=25&after_seq=10");
  });
  it("verify", async () => {
    expect((await api.audit.verify()).ok).toBe(true);
  });
});

describe("ops", () => {
  it("status", async () => {
    expect((await api.ops.status()).demo_mode).toBe(true);
  });
  it("freeze uses the ops_freeze CSRF purpose and a non-empty reason", async () => {
    await api.ops.freeze({ frozen: false, reason: "resume" });
    expect(callsTo("GET", "/auth/csrf")[0]?.search).toBe("?purpose=ops_freeze");
    expect(callsTo("POST", "/ops/freeze")[0]?.body).toEqual({ frozen: false, reason: "resume" });
  });
  it("freeze rejects a blank reason locally", async () => {
    await expect(api.ops.freeze({ frozen: true, reason: "  " })).rejects.toMatchObject({
      code: "VALIDATION_ERROR",
    });
    expect(calls).toHaveLength(0);
  });
});

describe("bff", () => {
  it("buyerHome", async () => {
    const r = await api.bff.buyerHome();
    expect(r.mandates).toHaveLength(1);
    expect(r.active_case?.state).toBe("OFFERED");
  });
  it("order tolerates null legs", async () => {
    const r = await api.bff.order(IDS.order);
    expect(r.order.order_id).toBe(IDS.order);
  });
  it("merchantQueue allows a null pending count", async () => {
    expect((await api.bff.merchantQueue()).tracking_pending).toBe(3);
  });
});
