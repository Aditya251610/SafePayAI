import * as React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { server } from "../../mocks/server";
import { callsTo, recorded } from "../../mocks/handlers";
import * as f from "../../mocks/fixtures";
import { answer, renderApp } from "./helpers";
import { reportCaseResponseSchema } from "@/lib/api/schemas/resolution";
import { saveReport } from "@/lib/storage/entries";

let params: Record<string, string> = { id: f.IDS.case };
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useParams: () => params,
  usePathname: () => "/cases/x",
}));
vi.mock("@/lib/api/config", () => ({ API_BASE_URL: "http://gateway.test/api" }));

import { CaseView, acceptResult } from "@/components/cases/case-view";
import { ApproveView } from "@/components/cases/approve-view";

const caseBody = (over: Record<string, unknown> = {}) => ({
  case_id: f.IDS.case,
  order_id: f.IDS.order,
  state: "OFFERED",
  version: 2,
  kind: "LATE",
  origin: "BUYER_REPORT",
  opened_at: f.ISO,
  window_hold: false,
  timeline: [],
  decision: null,
  offer: null,
  refund: null,
  queued_reason: null,
  ...over,
});

function seedReport(offerOver: Record<string, unknown> = {}) {
  saveReport(
    reportCaseResponseSchema.parse({
      case_id: f.IDS.case,
      state: "OFFERED",
      kind: "LATE",
      origin: "BUYER_REPORT",
      reasons: [{ code: "IN_TERMS", text: "Order inside mandate" }],
      offer: { ...f.offer, ...offerOver },
      protection: {},
    }),
  );
}

beforeEach(() => {
  params = { id: f.IDS.case };
  answer("get", `/resolution/cases/${f.IDS.case}`, 200, caseBody());
});
afterEach(() => window.sessionStorage.clear());

describe("acceptResult", () => {
  it.each([
    ["DONE", "REQUESTED", "Refund sent."],
    ["IN_PROGRESS", "REQUESTED", "Refund in progress."],
    ["QUEUED_FROZEN", "NONE", "Refund queued. Refunds are paused."],
    ["NOT_STARTED", "NONE", "Refund in progress."],
    ["DONE", "FAILED", "Refund did not go through."],
  ])("%s with refund %s reads %s", (execution, refund, title) => {
    expect(acceptResult(execution, refund).title).toBe(title);
  });
  it("never says sent unless the server says done", () => {
    expect(acceptResult("IN_PROGRESS", "SENT").title).not.toMatch(/sent/i);
  });
});

describe("CaseView", () => {
  it("shows the case, its rail and where it came from", async () => {
    renderApp(<CaseView />);
    expect(await screen.findByText("Your report")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Case progress" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /ORD-/ })).toHaveAttribute(
      "href",
      `/orders/${f.IDS.order}`,
    );
  });

  it("shows the kept offer and accepts it with the server's hash", async () => {
    seedReport();
    renderApp(<CaseView />);
    expect(await screen.findByText("Refund $48.20")).toBeInTheDocument();
    expect(screen.getByText("Order inside mandate")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Accept offer" }));
    expect(await screen.findByText("Refund in progress.")).toBeInTheDocument();
    const call = callsTo("POST", `/resolution/offers/${f.IDS.offer}/accept`)[0];
    expect(call?.body).toEqual({ proposal_hash: "offer-hash-1" });
    expect(call?.headers["idempotency-key"]).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Accept offer" })).not.toBeInTheDocument();
  });

  it("explains a refund queued behind the freeze", async () => {
    seedReport();
    answer("post", `/resolution/offers/${f.IDS.offer}/accept`, 200, {
      case_id: f.IDS.case,
      state: "APPROVED",
      execution: "QUEUED_FROZEN",
      refund: { status: "NONE", paypal_refund_id: null },
    });
    renderApp(<CaseView />);
    await userEvent.click(await screen.findByRole("button", { name: "Accept offer" }));
    expect(await screen.findByText("Refund queued. Refunds are paused.")).toBeInTheDocument();
  });

  it("after a timeout reads the case and never posts again", async () => {
    seedReport();
    server.use(
      recorded("post", `/resolution/offers/${f.IDS.offer}/accept`, () =>
        HttpResponse.json({ error: "UPSTREAM_TIMEOUT", message: "t" }, { status: 504 }),
      ),
    );
    renderApp(<CaseView />);
    await userEvent.click(await screen.findByRole("button", { name: "Accept offer" }));
    expect(await screen.findByText("Checking what happened.")).toBeInTheDocument();
    expect(callsTo("POST", `/resolution/offers/${f.IDS.offer}/accept`)).toHaveLength(1);
    await waitFor(() =>
      expect(callsTo("GET", `/resolution/cases/${f.IDS.case}`).length).toBeGreaterThan(1),
    );
  });

  it("sends the chosen decline reason", async () => {
    seedReport();
    renderApp(<CaseView />);
    await userEvent.selectOptions(
      await screen.findByLabelText("Or decline, and say why"),
      "WANT_HUMAN",
    );
    await userEvent.click(screen.getByRole("button", { name: "Decline offer" }));
    expect(await screen.findByText("You declined the offer.")).toBeInTheDocument();
    expect(screen.getByText(/moves to a reviewer/)).toBeInTheDocument();
    expect(callsTo("POST", `/resolution/offers/${f.IDS.offer}/decline`)[0]?.body).toEqual({
      reason_code: "WANT_HUMAN",
    });
  });

  it("shows a stale offer error", async () => {
    seedReport();
    answer("post", `/resolution/offers/${f.IDS.offer}/accept`, 409, {
      error: "http_error",
      detail: "OFFER_NOT_ACTIVE",
      request_id: "r",
    });
    renderApp(<CaseView />);
    await userEvent.click(await screen.findByRole("button", { name: "Accept offer" }));
    expect(await screen.findByText("Offer expired or changed")).toBeInTheDocument();
  });

  it("does not offer accept on an approval-tier offer", async () => {
    seedReport({ tier: "APPROVE" });
    renderApp(<CaseView />);
    expect(await screen.findByText("Approval needed")).toBeInTheDocument();
    expect(screen.getByText(/Check your email for the approval link/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Accept offer" })).not.toBeInTheDocument();
  });

  it("says a person is reviewing when the case is with a reviewer", async () => {
    answer("get", `/resolution/cases/${f.IDS.case}`, 200, caseBody({ state: "HUMAN_REVIEW" }));
    renderApp(<CaseView />);
    expect(await screen.findByText("A person is reviewing this case.")).toBeInTheDocument();
    expect(screen.queryByText(/\$/)).not.toBeInTheDocument();
  });

  it("is honest when the offer is not available on this screen", async () => {
    renderApp(<CaseView />);
    expect(await screen.findByText("The offer is not shown on this screen")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Accept offer" })).not.toBeInTheDocument();
  });

  it("does not show an old kept offer once the case moved on", async () => {
    seedReport();
    answer("get", `/resolution/cases/${f.IDS.case}`, 200, caseBody({ state: "RESOLVED_REFUNDED" }));
    renderApp(<CaseView />);
    expect(await screen.findByText("Refund sent.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Accept offer" })).not.toBeInTheDocument();
  });

  it("explains a case that is not found and a malformed id", async () => {
    answer("get", `/resolution/cases/${f.IDS.case}`, 404, {
      error: "http_error",
      detail: "CASE_NOT_FOUND",
      request_id: "r",
    });
    const { unmount } = renderApp(<CaseView />);
    expect(await screen.findByText("Case not found")).toBeInTheDocument();
    unmount();
    params = { id: "nope" };
    renderApp(<CaseView />);
    expect(await screen.findByText("That link is not valid")).toBeInTheDocument();
  });
});

describe("ApproveView", () => {
  beforeEach(() => {
    params = { token: "tok-1" };
  });

  it("shows the exact refund before consent", async () => {
    renderApp(<ApproveView />);
    expect(await screen.findByRole("heading", { name: "Refund $60.00" })).toBeInTheDocument();
    expect(screen.getByText("Merchant-funded via PayPal")).toBeInTheDocument();
    expect(callsTo("POST", "/resolution/approvals/tok-1/consent")).toHaveLength(0);
  });

  it("consents with the proposal hash and an idempotency key", async () => {
    renderApp(<ApproveView />);
    await userEvent.click(await screen.findByRole("button", { name: "Approve" }));
    expect(await screen.findByText("Refund in progress.")).toBeInTheDocument();
    const call = callsTo("POST", "/resolution/approvals/tok-1/consent")[0];
    expect(call?.body).toMatchObject({ proposal_hash: "offer-hash-2" });
    expect((call?.body as { csrf_nonce: string }).csrf_nonce).toBeTruthy();
    expect(call?.headers["idempotency-key"]).toBeTruthy();
  });

  it.each([
    ["APPROVAL_EXPIRED", "Link expired"],
    ["APPROVAL_REPLAY", "Link already used"],
    ["APPROVAL_NOT_FOUND", "Link not valid"],
  ])("explains %s", async (code, title) => {
    answer("get", "/resolution/approvals/tok-1", 404, {
      error: "http_error",
      detail: code,
      request_id: "r",
    });
    renderApp(<ApproveView />);
    expect(await screen.findByText(title)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });

  it("after a timeout asks the buyer to check the case rather than consent again", async () => {
    server.use(
      recorded("post", "/resolution/approvals/tok-1/consent", () =>
        HttpResponse.json({ error: "UPSTREAM_TIMEOUT", message: "t" }, { status: 504 }),
      ),
    );
    renderApp(<ApproveView />);
    await userEvent.click(await screen.findByRole("button", { name: "Approve" }));
    expect(await screen.findByText("Checking what happened.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });

  it("shows a consent refusal", async () => {
    answer("post", "/resolution/approvals/tok-1/consent", 409, {
      error: "http_error",
      detail: "PROPOSAL_HASH_MISMATCH",
      request_id: "r",
    });
    renderApp(<ApproveView />);
    await userEvent.click(await screen.findByRole("button", { name: "Approve" }));
    expect(await screen.findByText("Offer expired or changed")).toBeInTheDocument();
  });
});
