import * as React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { server } from "../../mocks/server";
import { recorded, callsTo } from "../../mocks/handlers";
import * as f from "../../mocks/fixtures";
import { answer, renderApp } from "./helpers";
import { cartSchema } from "@/lib/api/schemas/checkout";
import { saveCart, saveLastOrder } from "@/lib/storage/entries";

const push = vi.fn();
const goTo = vi.fn();
let search = "";
let params: Record<string, string> = { id: f.IDS.cart };
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  useParams: () => params,
  useSearchParams: () => new URLSearchParams(search),
  usePathname: () => "/cart/x",
}));
vi.mock("@/lib/api/config", () => ({ API_BASE_URL: "http://gateway.test/api" }));
vi.mock("@/lib/checkout/navigate", () => ({ goTo: (u: string) => goTo(u) }));
vi.mock("@/lib/api/reconcile", async (orig) => {
  const real = await orig<typeof import("@/lib/api/reconcile")>();
  return {
    ...real,
    pollUntil: (r: never, s: never) => real.pollUntil(r, s, { intervalMs: 5, timeoutMs: 100 }),
  };
});

import { CartView } from "@/components/cart/cart-view";
import { CancelView, ReturnView } from "@/components/checkout/return-view";

beforeEach(() => {
  push.mockClear();
  goTo.mockClear();
  search = "";
  params = { id: f.IDS.cart };
  vi.spyOn(window.history, "replaceState").mockImplementation(() => undefined);
});
afterEach(() => {
  window.sessionStorage.clear();
  vi.restoreAllMocks();
});

function seedCart(over: Record<string, unknown> = {}) {
  saveCart({ cart: cartSchema.parse({ ...f.cart, ...over }), mandateId: f.IDS.mandate });
}

describe("CartView", () => {
  it("shows lines, rule results and the server's figures", async () => {
    seedCart();
    renderApp(<CartView />);
    expect(await screen.findByText("Rules decided")).toBeInTheDocument();
    expect(await screen.findByText("Wired earbuds")).toBeInTheDocument();
    expect(screen.getByText("Mandate rules")).toBeInTheDocument();
    expect(screen.getAllByText("$48.20").length).toBeGreaterThan(0);
    expect(await screen.findByText(/Left now \$160\.00/)).toBeInTheDocument();
    expect(screen.getByText("Approve $48.20 at Northwind?")).toBeInTheDocument();
  });

  it("creates the order and sends the buyer to the PayPal sandbox", async () => {
    seedCart();
    renderApp(<CartView />);
    await userEvent.click(await screen.findByRole("button", { name: "Approve cart" }));
    await waitFor(() => expect(goTo).toHaveBeenCalledWith(f.order.approve_url));
    const call = callsTo("POST", `/checkout/carts/${f.IDS.cart}/confirm`)[0];
    expect(call?.body).toEqual({ proposal_hash: "hash-1" });
    expect(call?.headers["idempotency-key"]).toBeTruthy();
    expect(JSON.parse(window.sessionStorage.getItem("ps:last-order") ?? "{}").orderId).toBe(
      f.IDS.order,
    );
  });

  it("refuses to open a payment link that is not PayPal's sandbox", async () => {
    seedCart();
    answer("post", `/checkout/carts/${f.IDS.cart}/confirm`, 201, {
      order_id: f.IDS.order,
      status: "AWAITING_APPROVAL",
      approve_url: "https://evil.test/pay",
      total_minor: 4820,
      currency: "USD",
    });
    renderApp(<CartView />);
    await userEvent.click(await screen.findByRole("button", { name: "Approve cart" }));
    expect(await screen.findByText("Payment link not opened")).toBeInTheDocument();
    expect(goTo).not.toHaveBeenCalled();
  });

  it("offers no approve button on a blocked cart and says why", async () => {
    seedCart({
      status: "BLOCKED",
      checks: [
        { name: "mandate_evaluate", result: "BLOCK", reason_code: "OVER_CAP", source: "mandate" },
      ],
    });
    renderApp(<CartView />);
    expect(await screen.findByText("This cart cannot go ahead.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve cart" })).toBeDisabled();
    expect(screen.getAllByText("Over the cap").length).toBeGreaterThan(0);
  });

  it("keeps approve locked until the buyer confirms a cart that needs it", async () => {
    seedCart({ status: "NEEDS_CONFIRMATION" });
    renderApp(<CartView />);
    const approve = await screen.findByRole("button", { name: "Approve cart" });
    expect(approve).toBeDisabled();
    await userEvent.click(screen.getByLabelText("I read this and still want the cart"));
    expect(approve).toBeEnabled();
    await userEvent.click(approve);
    await waitFor(() => expect(goTo).toHaveBeenCalled());
    expect(callsTo("POST", `/checkout/carts/${f.IDS.cart}/confirm`)[0]?.body).toEqual({
      proposal_hash: "hash-1",
      confirm_intent_fit: true,
    });
  });

  it("disables approve and explains when money routes are off", async () => {
    seedCart();
    answer("get", "/ops/status", 200, {
      demo_mode: true,
      money_routes_enabled: false,
      refunds_frozen: "true",
      build_id: "t",
    });
    renderApp(<CartView />);
    expect(await screen.findByText("Money actions are switched off")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve cart" })).toBeDisabled();
  });

  it("after a timeout, looks for the order instead of posting again", async () => {
    seedCart();
    server.use(
      recorded("post", `/checkout/carts/${f.IDS.cart}/confirm`, () =>
        HttpResponse.json(
          { error: "UPSTREAM_TIMEOUT", message: "t", request_id: "r" },
          { status: 504 },
        ),
      ),
    );
    renderApp(<CartView />);
    await userEvent.click(await screen.findByRole("button", { name: "Approve cart" }));
    await waitFor(() => expect(goTo).toHaveBeenCalledWith(f.order.approve_url));
    expect(callsTo("POST", `/checkout/carts/${f.IDS.cart}/confirm`)).toHaveLength(1);
    expect(callsTo("GET", "/checkout/orders").length).toBeGreaterThan(0);
  });

  it("shows a server refusal", async () => {
    seedCart();
    answer("post", `/checkout/carts/${f.IDS.cart}/confirm`, 409, {
      error: "CART_CHANGED",
      detail: "changed",
      request_id: "r",
    });
    renderApp(<CartView />);
    await userEvent.click(await screen.findByRole("button", { name: "Approve cart" }));
    expect(await screen.findByText("The cart changed")).toBeInTheDocument();
    expect(goTo).not.toHaveBeenCalled();
  });

  it("says so when the cart is gone after a reload", async () => {
    renderApp(<CartView />);
    expect(await screen.findByText("This cart is no longer here")).toBeInTheDocument();
  });
});

describe("ReturnView", () => {
  it("completes the payment, removes PayPal's token from the address and shows success", async () => {
    saveLastOrder(f.IDS.order, f.IDS.mandate);
    search = "state=s1&token=tok&PayerID=payer";
    renderApp(<ReturnView />);
    expect(await screen.findByText("Payment captured.")).toBeInTheDocument();
    expect(callsTo("POST", "/checkout/orders/return")[0]?.body).toEqual({
      state: "s1",
      token: "tok",
      payer_id: "payer",
    });
    expect(window.history.replaceState).toHaveBeenCalledWith(null, "", "/checkout/return");
    expect(screen.getByRole("link", { name: "Track order" })).toHaveAttribute(
      "href",
      `/orders/${f.IDS.order}`,
    );
  });

  it("calls a pending payment pending, keeps reading the order, and lets it settle", async () => {
    search = "state=s1&token=tok&PayerID=payer";
    answer("post", "/checkout/orders/return", 200, {
      order_id: f.IDS.order,
      status: "CAPTURE_PENDING",
      message_code: "PENDING_PROTECTION_NOT_STARTED",
    });
    answer("get", `/checkout/orders/${f.IDS.order}`, 200, f.capturedOrder);
    renderApp(<ReturnView />);
    expect(await screen.findByText("Payment captured.")).toBeInTheDocument();
    expect(callsTo("GET", `/checkout/orders/${f.IDS.order}`).length).toBeGreaterThan(0);
  });

  it("after a timeout reads the order from the saved id and never says it failed", async () => {
    saveLastOrder(f.IDS.order, f.IDS.mandate);
    search = "state=s1&token=tok&PayerID=payer";
    server.use(
      recorded("post", "/checkout/orders/return", () =>
        HttpResponse.json({ error: "UPSTREAM_TIMEOUT", message: "t" }, { status: 504 }),
      ),
    );
    answer("get", `/checkout/orders/${f.IDS.order}`, 200, f.capturedOrder);
    renderApp(<ReturnView />);
    expect(await screen.findByText("Payment captured.")).toBeInTheDocument();
    expect(callsTo("POST", "/checkout/orders/return")).toHaveLength(1);
  });

  it("offers a manual payment check when the status stays unknown", async () => {
    search = "state=s1&token=tok&PayerID=payer";
    answer("post", "/checkout/orders/return", 200, {
      order_id: f.IDS.order,
      status: "CAPTURE_UNKNOWN",
      message_code: "TRY_AGAIN",
    });
    answer("get", `/checkout/orders/${f.IDS.order}`, 200, {
      ...f.order,
      status: "CAPTURE_UNKNOWN",
    });
    renderApp(<ReturnView />);
    expect(await screen.findByText("We could not confirm the payment.")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Check payment" })).toBeEnabled(),
    );
    await userEvent.click(screen.getByRole("button", { name: "Check payment" }));
    expect(await screen.findByText("Payment captured.")).toBeInTheDocument();
    expect(callsTo("POST", `/checkout/orders/${f.IDS.order}/capture`)).toHaveLength(1);
  });

  it("explains a revoked mandate and links to it", async () => {
    saveLastOrder(f.IDS.order, f.IDS.mandate);
    search = "state=s1&token=tok&PayerID=payer";
    answer("post", "/checkout/orders/return", 200, {
      order_id: f.IDS.order,
      status: "CANCELLED_REVOKED",
      message_code: "MANDATE_REVOKED",
    });
    renderApp(<ReturnView />);
    expect(await screen.findByText("Mandate was revoked. Order cancelled.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View mandate" })).toHaveAttribute(
      "href",
      `/mandate/${f.IDS.mandate}`,
    );
  });

  it("shows a rejected return and still points to the orders", async () => {
    search = "state=bad&token=tok&PayerID=payer";
    answer("post", "/checkout/orders/return", 400, {
      error: "STATE_INVALID",
      detail: "x",
      request_id: "r",
    });
    renderApp(<ReturnView />);
    expect(await screen.findByText("That PayPal return is not valid")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Your orders" })).toBeInTheDocument();
  });

  it("with no PayPal details and nothing saved, says there is nothing to finish", async () => {
    renderApp(<ReturnView />);
    expect(await screen.findByText("Nothing to finish here")).toBeInTheDocument();
    expect(callsTo("POST", "/checkout/orders/return")).toHaveLength(0);
  });

  it("with no PayPal details but a saved order, reads that order", async () => {
    saveLastOrder(f.IDS.order, f.IDS.mandate);
    answer("get", `/checkout/orders/${f.IDS.order}`, 200, f.capturedOrder);
    renderApp(<ReturnView />);
    expect(await screen.findByText("Payment captured.")).toBeInTheDocument();
  });
});

describe("CancelView", () => {
  it("records the cancellation and says no payment was captured", async () => {
    search = "state=c1";
    renderApp(<CancelView />);
    expect(
      await screen.findByText("You left PayPal. The order was cancelled."),
    ).toBeInTheDocument();
    expect(callsTo("POST", "/checkout/orders/cancel")[0]?.body).toEqual({ state: "c1" });
    expect(screen.getByText(/No payment was captured/)).toBeInTheDocument();
  });
  it("shows a rejected cancel", async () => {
    search = "state=bad";
    answer("post", "/checkout/orders/cancel", 400, {
      error: "STATE_INVALID",
      detail: "x",
      request_id: "r",
    });
    renderApp(<CancelView />);
    expect(await screen.findByText("That PayPal return is not valid")).toBeInTheDocument();
  });
});
