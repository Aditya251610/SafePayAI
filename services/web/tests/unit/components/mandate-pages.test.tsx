import * as React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as f from "../../mocks/fixtures";
import { callsTo } from "../../mocks/handlers";
import { answer, renderApp } from "./helpers";

const push = vi.fn();
let routeParams: Record<string, string> = { id: f.IDS.mandate };
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  useParams: () => routeParams,
  usePathname: () => "/home",
}));
vi.mock("@/lib/api/config", () => ({ API_BASE_URL: "http://gateway.test/api" }));

import HomePage from "@/app/(buyer)/home/page";
import { MandateForm } from "@/components/mandate/mandate-form";
import { MandateDetail } from "@/components/mandate/mandate-detail";

beforeEach(() => {
  push.mockClear();
  routeParams = { id: f.IDS.mandate };
});

describe("Home", () => {
  it("shows mandates, the latest order and the active case from one read", async () => {
    renderApp(<HomePage />);
    expect(await screen.findByText("Headphones under $150")).toBeInTheDocument();
    expect(screen.getByText(/\$340\.00/)).toBeInTheDocument();
    expect(screen.getByText(/of \$500\.00/)).toBeInTheDocument();
    expect(screen.getByText("Wired earbuds · Oct 17, 2026")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View order →" })).toHaveAttribute(
      "href",
      `/orders/${f.IDS.order}`,
    );
    expect(screen.getByRole("link", { name: "Open case →" })).toHaveAttribute(
      "href",
      `/cases/${f.IDS.case}`,
    );
    expect(screen.getByRole("list", { name: "Case progress" })).toBeInTheDocument();
  });

  it("keeps the page when each leg is empty", async () => {
    answer("get", "/bff/buyer-home", 200, { mandates: [], latest_order: null, active_case: null });
    renderApp(<HomePage />);
    expect(await screen.findByText("No mandate yet.")).toBeInTheDocument();
    expect(screen.getByText("No orders yet.")).toBeInTheDocument();
    expect(screen.getByText("No open case.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign your first mandate" })).toHaveAttribute(
      "href",
      "/mandate/new",
    );
  });

  it("explains a failed load and offers a retry", async () => {
    answer("get", "/bff/buyer-home", 500, {
      error: "internal_error",
      message: "boom",
      request_id: "r9",
    });
    renderApp(<HomePage />);
    expect(await screen.findByText("Something went wrong on our side")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("links to shopping and to a new mandate", async () => {
    renderApp(<HomePage />);
    expect(screen.getByRole("link", { name: "State what you need" })).toHaveAttribute(
      "href",
      "/intent",
    );
    expect(screen.getByRole("link", { name: "New mandate" })).toHaveAttribute(
      "href",
      "/mandate/new",
    );
  });
});

async function fillValidForm() {
  await userEvent.click(await screen.findByLabelText(/Northwind/));
  await userEvent.type(
    screen.getByLabelText("What should the agent buy?"),
    "Headphones under $150",
  );
}

describe("MandateForm", () => {
  it("lists shops from the catalog and starts with a locked sign button", async () => {
    renderApp(<MandateForm />);
    expect(await screen.findByLabelText(/Northwind/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign mandate" })).toBeDisabled();
    expect(screen.getByText("Awaiting signature")).toBeInTheDocument();
  });

  it("will not preview an incomplete form and says what is missing", async () => {
    renderApp(<MandateForm />);
    await screen.findByLabelText(/Northwind/);
    await userEvent.click(screen.getByRole("button", { name: "Preview terms" }));
    expect(await screen.findByText("Tick at least one shop.")).toBeInTheDocument();
    expect(screen.getByText("Say in plain words what the agent should buy.")).toBeInTheDocument();
    expect(callsTo("POST", "/mandate/mandates/preview")).toHaveLength(0);
  });

  it("previews, shows the exact text, then signs that text and opens the mandate", async () => {
    renderApp(<MandateForm />);
    await fillValidForm();
    await userEvent.click(screen.getByRole("button", { name: "Preview terms" }));
    expect(await screen.findByText(f.preview.screen_text)).toBeInTheDocument();
    expect(screen.getByText("Ready to sign")).toBeInTheDocument();

    const body = callsTo("POST", "/mandate/mandates/preview")[0]?.body as {
      terms: Record<string, unknown>;
    };
    expect(body.terms.max_total_minor).toBe(50000);

    await userEvent.click(screen.getByRole("button", { name: "Sign mandate" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/mandate/${f.IDS.mandate}`));

    const sign = callsTo("POST", "/mandate/mandates")[0];
    expect(sign?.body).toMatchObject({
      screen_text_hash: f.preview.screen_text_hash,
      nonce: f.preview.nonce,
      terms: f.preview.normalized_terms,
    });
    expect(sign?.headers["idempotency-key"]).toBeTruthy();
  });

  it("marks the preview stale as soon as a field changes", async () => {
    renderApp(<MandateForm />);
    await fillValidForm();
    await userEvent.click(screen.getByRole("button", { name: "Preview terms" }));
    await screen.findByText("Ready to sign");
    await userEvent.type(screen.getByLabelText("What should the agent buy?"), "!");
    expect(await screen.findByText("Form changed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign mandate" })).toBeDisabled();
  });

  it("asks for a fresh preview when the server rejects the nonce", async () => {
    answer("post", "/mandate/mandates", 409, {
      error: { code: "NONCE_INVALID", message: "nonce", details: {} },
      request_id: "r1",
    });
    renderApp(<MandateForm />);
    await fillValidForm();
    await userEvent.click(screen.getByRole("button", { name: "Preview terms" }));
    await screen.findByText("Ready to sign");
    await userEvent.click(screen.getByRole("button", { name: "Sign mandate" }));
    expect(await screen.findByText("Terms refreshed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign mandate" })).toBeDisabled();
    expect(push).not.toHaveBeenCalled();
  });

  it("puts a bounds error from the server on the right input", async () => {
    answer("post", "/mandate/mandates/preview", 422, {
      error: {
        code: "TERMS_OUT_OF_BOUNDS",
        message: "Cap is above the allowed limit.",
        details: { field: "max_total_minor" },
      },
      request_id: "r2",
    });
    renderApp(<MandateForm />);
    await fillValidForm();
    await userEvent.click(screen.getByRole("button", { name: "Preview terms" }));
    const cap = await screen.findByLabelText("Total cap (USD)");
    await waitFor(() => expect(cap).toHaveAttribute("aria-invalid", "true"));
    expect(screen.getByText("Cap is above the allowed limit.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign mandate" })).toBeDisabled();
  });

  it("tells the buyer when money routes are switched off", async () => {
    answer("post", "/mandate/mandates", 503, { error: "MONEY_ROUTES_DISABLED", message: "off" });
    renderApp(<MandateForm />);
    await fillValidForm();
    await userEvent.click(screen.getByRole("button", { name: "Preview terms" }));
    await screen.findByText("Ready to sign");
    await userEvent.click(screen.getByRole("button", { name: "Sign mandate" }));
    expect(await screen.findByText("Money actions are switched off")).toBeInTheDocument();
  });

  it("counts intent characters and strips line breaks", async () => {
    renderApp(<MandateForm />);
    const intent = await screen.findByLabelText("What should the agent buy?");
    await userEvent.type(intent, "ab{enter}cd");
    expect(intent).toHaveValue("ab cd");
    expect(screen.getByText("5 / 500")).toBeInTheDocument();
  });
});

describe("MandateDetail", () => {
  it("shows the server's spend, terms and protection", async () => {
    renderApp(<MandateDetail />);
    expect(await screen.findByText("$340.00")).toBeInTheDocument();
    expect(screen.getByText(/of \$500\.00 · \$160\.00 left/)).toBeInTheDocument();
    expect(screen.getByText("Northwind Audio")).toBeInTheDocument();
    expect(screen.getByText("$50.00")).toBeInTheDocument();
    expect(screen.getByText(/Delivery due in 7 days/)).toBeInTheDocument();
    expect(await screen.findByText("FUTURE_ONLY")).toBeInTheDocument();
  });

  it("revokes after an in-page confirmation, sending the chosen reason", async () => {
    renderApp(<MandateDetail />);
    await screen.findByText("$340.00");
    await userEvent.selectOptions(screen.getByLabelText("Reason"), "SPENDING_TOO_HIGH");
    await userEvent.click(screen.getByRole("button", { name: "Revoke mandate" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Revoke this mandate?")).toBeInTheDocument();
    expect(callsTo("POST", `/mandate/mandates/${f.IDS.mandate}/revoke`)).toHaveLength(0);
    await userEvent.click(within(dialog).getByRole("button", { name: "Yes, revoke" }));
    expect(await screen.findByText("Mandate revoked")).toBeInTheDocument();
    expect(callsTo("POST", `/mandate/mandates/${f.IDS.mandate}/revoke`)[0]?.body).toEqual({
      reason_code: "SPENDING_TOO_HIGH",
    });
  });

  it("offers no revoke on a mandate that is already revoked", async () => {
    answer("get", `/mandate/mandates/${f.IDS.mandate}`, 200, {
      ...f.mandate,
      status: "revoked",
      revoked_at: f.ISO,
    });
    renderApp(<MandateDetail />);
    expect(await screen.findByText(/Revoked on/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Revoke mandate" })).not.toBeInTheDocument();
  });

  it("rejects a malformed id without calling the gateway", async () => {
    routeParams = { id: "preview" };
    renderApp(<MandateDetail />);
    expect(await screen.findByText("That link is not valid")).toBeInTheDocument();
    expect(callsTo("GET", "/mandate/mandates/preview")).toHaveLength(0);
  });

  it("explains a mandate that is not found", async () => {
    answer("get", `/mandate/mandates/${f.IDS.mandate}`, 404, {
      error: { code: "MANDATE_NOT_FOUND", message: "x", details: {} },
      request_id: "r",
    });
    renderApp(<MandateDetail />);
    expect(await screen.findByText("Mandate not found")).toBeInTheDocument();
  });
});
