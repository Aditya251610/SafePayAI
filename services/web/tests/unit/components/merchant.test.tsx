import * as React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { server } from "../../mocks/server";
import { callsTo, recorded } from "../../mocks/handlers";
import * as f from "../../mocks/fixtures";
import { answer, renderApp } from "./helpers";

let params: Record<string, string> = { id: f.IDS.case };
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useParams: () => params,
  usePathname: () => "/merchant",
}));
vi.mock("next-themes", () => ({ useTheme: () => ({ resolvedTheme: "dark", setTheme: vi.fn() }) }));
vi.mock("@/lib/api/config", () => ({ API_BASE_URL: "http://gateway.test/api" }));

import { MerchantDesk } from "@/components/merchant/merchant-desk";
import { MerchantCase } from "@/components/merchant/merchant-case";
import { RoleShell } from "@/components/shell/any-role-shell";
import { SessionProvider } from "@/lib/auth/session";

const kase = (state: string, id: string = f.IDS.case) => ({ ...f.caseItem, case_id: id, state });

describe("MerchantDesk", () => {
  it("lists the queue and narrows it on the client", async () => {
    answer("get", "/bff/merchant-queue", 200, {
      cases: [
        kase("OFFERED"),
        kase("HUMAN_REVIEW", "99999999-9999-4999-8999-999999999999"),
        kase("DECLINED", "88888888-8888-4888-8888-888888888888"),
      ],
      tracking_pending: 3,
    });
    renderApp(<MerchantDesk />);
    expect(await screen.findByText("3 shipments in motion")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Open" })).toHaveLength(3);
    await userEvent.click(screen.getByRole("button", { name: "With a reviewer" }));
    expect(screen.getAllByRole("link", { name: "Open" })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "With a reviewer" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("still loads when the pending count is null", async () => {
    answer("get", "/bff/merchant-queue", 200, { cases: [kase("OFFERED")], tracking_pending: null });
    renderApp(<MerchantDesk />);
    expect(await screen.findByText("Tracking count unavailable")).toBeInTheDocument();
    expect(screen.getByText(/tracking_pending is null/)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Open" })).toHaveLength(1);
  });

  it("shows an empty queue and a failed queue", async () => {
    answer("get", "/bff/merchant-queue", 200, { cases: [], tracking_pending: 0 });
    const { unmount } = renderApp(<MerchantDesk />);
    expect(await screen.findByText("No cases here.")).toBeInTheDocument();
    unmount();
    answer("get", "/bff/merchant-queue", 500, { error: "internal_error", message: "x" });
    renderApp(<MerchantDesk />);
    expect(await screen.findAllByText("Something went wrong on our side")).not.toHaveLength(0);
  });

  it("asks for a mandate before listing orders, then fills the ship form from a row", async () => {
    renderApp(<MerchantDesk />);
    await userEvent.type(await screen.findByLabelText("Mandate id"), "nope");
    await userEvent.click(screen.getByRole("button", { name: "Show orders" }));
    expect(await screen.findByText("Paste a mandate id.")).toBeInTheDocument();
    expect(callsTo("GET", "/checkout/orders")).toHaveLength(0);

    await userEvent.clear(screen.getByLabelText("Mandate id"));
    await userEvent.type(screen.getByLabelText("Mandate id"), f.IDS.mandate);
    await userEvent.click(screen.getByRole("button", { name: "Show orders" }));
    await userEvent.click(await screen.findByRole("button", { name: "Ship this" }));
    expect(screen.getByLabelText("Order id")).toHaveValue(f.IDS.order);
    expect(callsTo("GET", "/checkout/orders")[0]?.search).toContain(`mandate_id=${f.IDS.mandate}`);
  });

  it("marks an order shipped and labels the carrier simulated", async () => {
    renderApp(<MerchantDesk />);
    await userEvent.type(await screen.findByLabelText("Order id"), f.IDS.order);
    await userEvent.type(screen.getByLabelText("Tracking number"), "TRK-9");
    await userEvent.type(screen.getByLabelText("Carrier name"), "SimPost");
    await userEvent.selectOptions(screen.getByLabelText("Outcome profile"), "LATE");
    await userEvent.click(screen.getByRole("button", { name: "Mark shipped" }));
    expect(await screen.findByText("Marked shipped")).toBeInTheDocument();
    expect(screen.getByText(/SIMULATED CARRIER/)).toBeInTheDocument();
    const call = callsTo("POST", "/tracking/shipments")[0];
    expect(call?.body).toEqual({
      order_id: f.IDS.order,
      tracking_number: "TRK-9",
      carrier_name: "SimPost",
      outcome_profile: "LATE",
    });
    expect(call?.headers["idempotency-key"]).toBeTruthy();
  });

  it("checks the ship form and explains an unpaid order", async () => {
    renderApp(<MerchantDesk />);
    await userEvent.click(await screen.findByRole("button", { name: "Mark shipped" }));
    expect(await screen.findByText("Paste the order id.")).toBeInTheDocument();
    expect(screen.getByText("Enter a tracking number.")).toBeInTheDocument();
    expect(callsTo("POST", "/tracking/shipments")).toHaveLength(0);

    answer("post", "/tracking/shipments", 409, {
      error: "http_error",
      detail: "ORDER_NOT_CAPTURED",
      request_id: "r",
    });
    await userEvent.type(screen.getByLabelText("Order id"), f.IDS.order);
    await userEvent.type(screen.getByLabelText("Tracking number"), "T");
    await userEvent.type(screen.getByLabelText("Carrier name"), "C");
    await userEvent.click(screen.getByRole("button", { name: "Mark shipped" }));
    expect(await screen.findByText("That order is not paid yet")).toBeInTheDocument();
  });
});

function caseAs(state: string) {
  answer("get", `/resolution/cases/${f.IDS.case}`, 200, {
    case_id: f.IDS.case,
    order_id: f.IDS.order,
    state,
    version: 1,
    kind: "LATE",
    origin: "DETECTOR",
    opened_at: f.ISO,
    window_hold: false,
  });
}

describe("MerchantCase", () => {
  beforeEach(() => {
    params = { id: f.IDS.case };
  });

  it("shows the carrier record as simulated and has no amount field", async () => {
    caseAs("OFFERED");
    renderApp(<MerchantCase />);
    expect(await screen.findByText("No amount field.")).toBeInTheDocument();
    expect(await screen.findByText(/in transit/)).toBeInTheDocument();
    expect(screen.getByText("Simulated carrier")).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("asks for confirmation, then sends only the action type", async () => {
    caseAs("OFFERED");
    renderApp(<MerchantCase />);
    await userEvent.click(await screen.findByRole("button", { name: "Override the offer" }));
    const dialog = await screen.findByRole("dialog");
    expect(callsTo("POST", `/resolution/cases/${f.IDS.case}/merchant-action`)).toHaveLength(0);
    await userEvent.click(within(dialog).getByRole("button", { name: "Yes, continue" }));
    expect(await screen.findByText("Done")).toBeInTheDocument();
    const call = callsTo("POST", `/resolution/cases/${f.IDS.case}/merchant-action`)[0];
    expect(call?.body).toEqual({ type: "OVERRIDE_OFFER" });
    expect(call?.headers["idempotency-key"]).toBeTruthy();
  });

  it("offers only the actions the case state allows", async () => {
    caseAs("HUMAN_REVIEW");
    renderApp(<MerchantCase />);
    expect(await screen.findByRole("button", { name: "Override the offer" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Confirm a reship" })).toBeDisabled();
    caseAs("DECLINED");
  });

  it("allows override but not reship from declined", async () => {
    caseAs("DECLINED");
    renderApp(<MerchantCase />);
    expect(await screen.findByRole("button", { name: "Override the offer" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Confirm a reship" })).toBeDisabled();
  });

  it("tells the merchant when the case moved", async () => {
    caseAs("OFFERED");
    server.use(
      recorded("post", `/resolution/cases/${f.IDS.case}/merchant-action`, () =>
        HttpResponse.json(
          { error: "http_error", detail: "ILLEGAL_TRANSITION", request_id: "r" },
          { status: 409 },
        ),
      ),
    );
    renderApp(<MerchantCase />);
    await userEvent.click(await screen.findByRole("button", { name: "Confirm a reship" }));
    await userEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Yes, continue" }),
    );
    expect(await screen.findByText("This case moved")).toBeInTheDocument();
    await waitFor(() =>
      expect(callsTo("GET", `/resolution/cases/${f.IDS.case}`).length).toBeGreaterThan(1),
    );
  });
});

describe("RoleShell for staff screens", () => {
  it("shows a use-a-larger-screen note and still renders the content for wide screens", async () => {
    answer("get", "/auth/me", 200, { ...f.me, role: "merchant", merchant_id: "mrc_northwind" });
    renderApp(
      <SessionProvider>
        <RoleShell roles={["merchant", "operator"]} desktopOnly>
          <p>Desk</p>
        </RoleShell>
      </SessionProvider>,
    );
    expect(await screen.findByText("Use a larger screen")).toBeInTheDocument();
    expect(screen.getByText("Desk").parentElement).toHaveClass("hidden", "md:block");
  });
  it("blocks other roles", async () => {
    answer("get", "/auth/me", 200, { ...f.me, role: "buyer" });
    renderApp(
      <SessionProvider>
        <RoleShell roles={["operator"]} desktopOnly>
          <p>Desk</p>
        </RoleShell>
      </SessionProvider>,
    );
    expect(await screen.findByText("Wrong account type")).toBeInTheDocument();
    expect(screen.queryByText("Desk")).not.toBeInTheDocument();
  });
});
