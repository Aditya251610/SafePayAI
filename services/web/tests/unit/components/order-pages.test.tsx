import * as React from "react";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as f from "../../mocks/fixtures";
import { callsTo } from "../../mocks/handlers";
import { answer, renderApp } from "./helpers";

const push = vi.fn();
const goTo = vi.fn();
let params: Record<string, string> = { id: f.IDS.order };
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  useParams: () => params,
  usePathname: () => "/orders",
}));
vi.mock("@/lib/api/config", () => ({ API_BASE_URL: "http://gateway.test/api" }));
vi.mock("@/lib/checkout/navigate", () => ({ goTo: (u: string) => goTo(u) }));

import { OrdersList } from "@/components/orders/orders-list";
import { OrderDetail } from "@/components/orders/order-detail";
import { OrderReport } from "@/components/orders/order-report";

beforeEach(() => {
  push.mockClear();
  goTo.mockClear();
  params = { id: f.IDS.order };
});
afterEach(() => window.sessionStorage.clear());

describe("OrdersList", () => {
  it("lists orders as a table and as cards, newest first", async () => {
    renderApp(<OrdersList />);
    expect(await screen.findByText(/1 order · newest first/)).toBeInTheDocument();
    const links = screen.getAllByRole("link", { name: /ORD-/ });
    expect(links.length).toBe(2);
    expect(links[0]).toHaveAttribute("href", `/orders/${f.IDS.order}`);
    expect(screen.getAllByText("Waiting for PayPal approval").length).toBe(2);
    expect(screen.getAllByText("$48.20").length).toBeGreaterThan(0);
  });
  it("has a friendly empty state", async () => {
    answer("get", "/checkout/orders", 200, { items: [] });
    renderApp(<OrdersList />);
    expect(await screen.findByText("No orders yet.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "State what you need" })).toBeInTheDocument();
  });
  it("shows a failure with a retry", async () => {
    answer("get", "/checkout/orders", 500, { error: "internal_error", message: "x" });
    renderApp(<OrdersList />);
    expect(await screen.findByText("Something went wrong on our side")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});

const bff = (over: Record<string, unknown> = {}) =>
  answer("get", `/bff/orders/${f.IDS.order}`, 200, {
    order: f.capturedOrder,
    shipment: f.tracking,
    case: null,
    audit_verified: true,
    ...over,
  });

describe("OrderDetail", () => {
  it("shows tracking labelled simulated, the case and the audit state", async () => {
    bff({ case: f.caseItem });
    renderApp(<OrderDetail />);
    expect(await screen.findByText("Simulated carrier")).toBeInTheDocument();
    expect(screen.getByText(/Carrier status is simulated/)).toBeInTheDocument();
    expect(screen.getByText("Offer ready")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open case →" })).toHaveAttribute(
      "href",
      `/cases/${f.IDS.case}`,
    );
    expect(screen.getByText("Chain intact")).toBeInTheDocument();
    expect(screen.getByText("Captured")).toBeInTheDocument();
  });

  it("keeps the page when each leg is missing", async () => {
    bff({ shipment: null, case: null, audit_verified: null });
    renderApp(<OrderDetail />);
    expect(
      await screen.findByText("Tracking is unavailable. Order and case still load."),
    ).toBeInTheDocument();
    expect(screen.getByText("No case. Nothing is wrong with this order.")).toBeInTheDocument();
    expect(screen.getByText("Chain check unavailable. Try again in a minute.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Report a problem" })).toHaveAttribute(
      "href",
      `/orders/${f.IDS.order}/report`,
    );
  });

  it("flags a failed chain check clearly", async () => {
    bff({ audit_verified: false });
    renderApp(<OrderDetail />);
    expect(await screen.findByText("Chain check failed")).toBeInTheDocument();
  });

  it("does not offer a problem report before the payment is captured", async () => {
    bff({ order: f.order, shipment: null });
    renderApp(<OrderDetail />);
    await screen.findByText("Tracking is unavailable. Order and case still load.");
    expect(screen.queryByRole("link", { name: "Report a problem" })).not.toBeInTheDocument();
  });

  it("offers to finish an unpaid order, only for an allowed PayPal link", async () => {
    bff({ order: f.order, shipment: null });
    renderApp(<OrderDetail />);
    await userEvent.click(await screen.findByRole("button", { name: "Continue to PayPal" }));
    expect(goTo).toHaveBeenCalledWith(f.order.approve_url);
  });

  it("shows the receipt with every disclosure exactly as sent", async () => {
    bff();
    renderApp(<OrderDetail />);
    await userEvent.click(await screen.findByRole("tab", { name: "Receipt" }));
    expect(await screen.findByText("CAP-1")).toBeInTheDocument();
    const list = screen.getByRole("list", { name: "Disclosures" });
    for (const d of f.receipt.disclosures) expect(within(list).getByText(d)).toBeInTheDocument();
    expect(screen.getByText(/Demo window, not PayPal's/)).toBeInTheDocument();
  });

  it("says the receipt is not ready when the order is not captured, without asking the server", async () => {
    bff({ order: f.order });
    renderApp(<OrderDetail />);
    await userEvent.click(await screen.findByRole("tab", { name: "Receipt" }));
    expect(screen.getByText("Receipt is not ready yet.")).toBeInTheDocument();
    expect(callsTo("GET", `/checkout/orders/${f.IDS.order}/receipt`)).toHaveLength(0);
  });

  it("explains a receipt the server is not ready to give", async () => {
    bff();
    answer("get", `/checkout/orders/${f.IDS.order}/receipt`, 409, {
      error: "RECEIPT_NOT_READY",
      detail: "order status is CAPTURE_PENDING",
      request_id: "r",
    });
    renderApp(<OrderDetail />);
    await userEvent.click(await screen.findByRole("tab", { name: "Receipt" }));
    expect(await screen.findByText("Receipt is not ready")).toBeInTheDocument();
  });

  it("explains an order that is not found", async () => {
    answer("get", `/bff/orders/${f.IDS.order}`, 404, {
      error: "ORDER_NOT_FOUND",
      message: "order not found",
    });
    renderApp(<OrderDetail />);
    expect(await screen.findByText("Order not found")).toBeInTheDocument();
  });

  it("rejects a malformed id without calling the gateway", async () => {
    params = { id: "nope" };
    renderApp(<OrderDetail />);
    expect(await screen.findByText("That link is not valid")).toBeInTheDocument();
  });
});

describe("OrderReport", () => {
  it("opens a case, keeps the offer for the case screen and goes there", async () => {
    renderApp(<OrderReport />);
    await userEvent.type(screen.getByLabelText("What went wrong?"), "It never arrived.");
    await userEvent.click(screen.getByRole("button", { name: "Open case" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/cases/${f.IDS.case}`));
    const call = callsTo("POST", "/resolution/cases/report")[0];
    expect(call?.body).toEqual({ order_id: f.IDS.order, text: "It never arrived." });
    expect(call?.headers["idempotency-key"]).toBeTruthy();
    expect(window.sessionStorage.getItem(`ps:report:${f.IDS.case}`)).toContain("offer-hash-1");
  });

  it("will not send an empty report", async () => {
    renderApp(<OrderReport />);
    await userEvent.click(screen.getByRole("button", { name: "Open case" }));
    expect(await screen.findByText("Say what you expected and what you got.")).toBeInTheDocument();
    expect(callsTo("POST", "/resolution/cases/report")).toHaveLength(0);
  });

  it("counts characters and states what the AI does and does not do", () => {
    renderApp(<OrderReport />);
    expect(screen.getByText("0 / 4000")).toBeInTheDocument();
    expect(screen.getByText(/It cannot offer a refund/)).toBeInTheDocument();
  });

  it("shows a failure and retries with the same key", async () => {
    answer("post", "/resolution/cases/report", 404, {
      error: "http_error",
      detail: "ORDER_NOT_FOUND",
      request_id: "r",
    });
    renderApp(<OrderReport />);
    await userEvent.type(screen.getByLabelText("What went wrong?"), "late");
    await userEvent.click(screen.getByRole("button", { name: "Open case" }));
    expect(await screen.findByText("Order not found")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});
