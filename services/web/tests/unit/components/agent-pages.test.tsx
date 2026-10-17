import * as React from "react";
import { act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as f from "../../mocks/fixtures";
import { callsTo } from "../../mocks/handlers";
import { answer, renderApp } from "./helpers";
import { cartSchema } from "@/lib/api/schemas/checkout";
import { proposalSchema } from "@/lib/api/schemas/agent";
import { saveProposal } from "@/lib/storage/entries";

const push = vi.fn();
let params: Record<string, string> = { proposal_id: "prop-1" };
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  useParams: () => params,
  usePathname: () => "/intent",
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/lib/api/config", () => ({ API_BASE_URL: "http://gateway.test/api" }));

import { IntentForm } from "@/components/intent/intent-form";
import { ProposalView } from "@/components/agent/proposal-view";
import { AgentWorking } from "@/components/agent/agent-working";

beforeEach(() => {
  push.mockClear();
  params = { proposal_id: "prop-1" };
});
afterEach(() => window.sessionStorage.clear());

describe("IntentForm", () => {
  it("asks for a mandate first when there is no active one", async () => {
    answer("get", "/bff/buyer-home", 200, { mandates: [], latest_order: null, active_case: null });
    renderApp(<IntentForm />);
    expect(await screen.findByText("You need an active mandate first.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign a mandate" })).toHaveAttribute(
      "href",
      "/mandate/new",
    );
  });

  it("shows the agent boundary from the mandate and the seeded-catalog disclosure", async () => {
    renderApp(<IntentForm />);
    expect(await screen.findByText("Agent boundary")).toBeInTheDocument();
    expect(screen.getByText("Northwind Audio")).toBeInTheDocument();
    expect(screen.getByText("$160.00")).toBeInTheDocument();
    expect(screen.getByText("Seeded · not live")).toBeInTheDocument();
  });

  it("proposes from words, keeps the answer for the next screen and goes there", async () => {
    renderApp(<IntentForm />);
    await userEvent.type(await screen.findByLabelText("What do you need?"), "earbuds under $60");
    await userEvent.click(screen.getByRole("button", { name: "Propose cart" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/agent/prop-1"));
    const call = callsTo("POST", "/agent/propose")[0];
    expect(call?.body).toEqual({
      mandate_id: f.IDS.mandate,
      mode: "intent",
      intent_text: "earbuds under $60",
    });
    expect(call?.headers["idempotency-key"]).toBeTruthy();
    expect(window.sessionStorage.getItem("ps:proposal:prop-1")).toContain("SKU-1");
  });

  it("will not send an empty ask", async () => {
    renderApp(<IntentForm />);
    await userEvent.click(await screen.findByRole("button", { name: "Propose cart" }));
    expect(await screen.findByText("Say in a few words what you need.")).toBeInTheDocument();
    expect(callsTo("POST", "/agent/propose")).toHaveLength(0);
  });

  it("fills the box from an example", async () => {
    renderApp(<IntentForm />);
    await userEvent.click(await screen.findByRole("button", { name: "Desk lamp, under $60" }));
    expect(screen.getByLabelText("What do you need?")).toHaveValue("Desk lamp, under $60");
  });

  it("sends the form mode with the budget in minor units", async () => {
    renderApp(<IntentForm initialMode="form" />);
    await userEvent.selectOptions(await screen.findByLabelText("Category"), "audio");
    await userEvent.type(screen.getByLabelText("Budget (USD)"), "60.50");
    await userEvent.click(screen.getByRole("button", { name: "Propose cart" }));
    await waitFor(() => expect(push).toHaveBeenCalled());
    expect(callsTo("POST", "/agent/propose")[0]?.body).toEqual({
      mandate_id: f.IDS.mandate,
      mode: "form",
      form: {
        category: "audio",
        max_budget_minor: 6050,
        quantity: 1,
        merchant_id: null,
        keywords: null,
      },
    });
  });

  it("validates the form fields before asking", async () => {
    renderApp(<IntentForm initialMode="form" />);
    await userEvent.click(await screen.findByRole("button", { name: "Propose cart" }));
    expect(await screen.findByText("Pick a category.")).toBeInTheDocument();
    expect(screen.getByText("Enter a budget, like 60.00.")).toBeInTheDocument();
    expect(callsTo("POST", "/agent/propose")).toHaveLength(0);
  });

  it("shows the failure and lets the buyer try again with the same key", async () => {
    answer("post", "/agent/propose", 503, {
      error: "MANDATE_UNAVAILABLE",
      detail: "MANDATE_UNAVAILABLE",
      request_id: "r",
    });
    renderApp(<IntentForm />);
    await userEvent.type(await screen.findByLabelText("What do you need?"), "lamp");
    await userEvent.click(screen.getByRole("button", { name: "Propose cart" }));
    expect(await screen.findByText("Mandate service is busy")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(callsTo("POST", "/agent/propose")).toHaveLength(2));
    const keys = callsTo("POST", "/agent/propose").map((c) => c.headers["idempotency-key"]);
    expect(keys[0]).toBe(keys[1]);
  });
});

function seed(over: Record<string, unknown> = {}) {
  saveProposal({
    proposal: proposalSchema.parse({ ...f.proposal, ...over }),
    mandateId: f.IDS.mandate,
  });
}

describe("ProposalView", () => {
  it("shows the draft, labelled as a draft that decides nothing", async () => {
    seed();
    renderApp(<ProposalView />);
    expect(await screen.findByText("Draft · decides nothing")).toBeInTheDocument();
    expect(screen.getByText("Wired earbuds")).toBeInTheDocument();
    expect(screen.getByText(/Draft confidence 82%/)).toBeInTheDocument();
    expect(screen.getByText("The agent cannot")).toBeInTheDocument();
  });

  it("builds the cart on request, keeps it and opens it", async () => {
    seed();
    renderApp(<ProposalView />);
    await userEvent.click(await screen.findByRole("button", { name: "Check against my mandate" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/cart/${f.IDS.cart}`));
    const call = callsTo("POST", "/checkout/carts")[0];
    expect(call?.body).toEqual({
      mandate_id: f.IDS.mandate,
      proposal_id: "prop-1",
      lines: [{ sku: "SKU-1", qty: 1 }],
    });
    expect(call?.headers["idempotency-key"]).toBeTruthy();
    expect(
      cartSchema.safeParse(
        JSON.parse(window.sessionStorage.getItem(`ps:cart:${f.IDS.cart}`) ?? "{}").cart,
      ).success,
    ).toBe(true);
  });

  it.each([
    ["NO_MATCH", "Nothing matched"],
    ["NO_PROPOSAL", "The agent could not build a cart"],
    ["AI_PAUSED", "The AI helper is paused"],
  ])("explains %s and offers another way", async (status, title) => {
    seed({ status, lines: [], no_match_reason: null });
    renderApp(<ProposalView />);
    expect(await screen.findByText(title)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Use the form" })).toHaveAttribute(
      "href",
      "/intent?mode=form",
    );
    expect(callsTo("POST", "/checkout/carts")).toHaveLength(0);
  });

  it("marks a cached answer", async () => {
    seed({ source: "cached" });
    renderApp(<ProposalView />);
    expect(await screen.findByText("Cached answer")).toBeInTheDocument();
  });

  it("says so when the proposal is gone after a reload", async () => {
    renderApp(<ProposalView />);
    expect(await screen.findByText("This proposal is no longer here")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "State what you need" })).toHaveAttribute(
      "href",
      "/intent",
    );
  });

  it("shows cart creation failures with a retry", async () => {
    seed();
    answer("post", "/checkout/carts", 503, {
      error: "MANDATE_UNAVAILABLE",
      detail: "x",
      request_id: "r",
    });
    renderApp(<ProposalView />);
    await userEvent.click(await screen.findByRole("button", { name: "Check against my mandate" }));
    expect(await screen.findByText("Mandate service is busy")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("renders untrusted titles as plain text", async () => {
    seed({ lines: [{ sku: "X", quantity: 1, display_title: "<img src=x onerror=alert(1)>" }] });
    const { container } = renderApp(<ProposalView />);
    expect(await screen.findByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
  });
});

describe("AgentWorking", () => {
  it("shows elapsed time and offers a retry after the 20 second watchdog", () => {
    const retry = vi.fn();
    const { rerender } = renderApp(<AgentWorking seconds={5} onRetry={retry} />);
    expect(screen.getByText("Elapsed 5 s")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
    rerender(<AgentWorking seconds={20} onRetry={retry} />);
    expect(screen.getByText(/Taking longer than expected/)).toBeInTheDocument();
    act(() => screen.getByRole("button", { name: "Try again" }).click());
    expect(retry).toHaveBeenCalledOnce();
  });
});
