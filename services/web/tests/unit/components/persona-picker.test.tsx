import * as React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../mocks/server";
import { TEST_BASE, callsTo, recorded } from "../../mocks/handlers";
import * as f from "../../mocks/fixtures";
import { makeQueryClient } from "@/lib/query/provider";

const replace = vi.fn();
let search = "";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(search),
  usePathname: () => "/login",
}));
vi.mock("@/lib/api/config", () => ({ API_BASE_URL: "http://gateway.test/api" }));

import { SessionProvider } from "@/lib/auth/session";
import { LoginPanels } from "@/components/login/login-panels";
import { groupPersonas, personaBlurb } from "@/lib/auth/personas";

function show() {
  const qc = makeQueryClient();
  qc.setDefaultOptions({ queries: { retry: false } });
  return render(
    <QueryClientProvider client={qc}>
      <SessionProvider>
        <LoginPanels />
      </SessionProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  replace.mockClear();
  search = "";
  server.use(
    http.get(`${TEST_BASE}/auth/me`, () =>
      HttpResponse.json({ error: "UNAUTHENTICATED", message: "x" }, { status: 401 }),
    ),
  );
});

describe("persona picker", () => {
  it("lists seeded accounts grouped by role", async () => {
    show();
    const select = await screen.findByLabelText("Account");
    const groups = within(select).getAllByRole("group");
    expect(groups.map((g) => g.getAttribute("label"))).toEqual([
      "Buyer",
      "Merchant",
      "Operator",
      "Reviewer",
    ]);
    expect(within(groups[0]!).getAllByRole("option")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Sign in as Persona Buyer" })).toBeInTheDocument();
  });

  it("shows the blurb for the chosen account", async () => {
    show();
    await userEvent.selectOptions(await screen.findByLabelText("Account"), "buyer-alex");
    expect(screen.getByText("A buyer with nothing yet - start from scratch")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Account"), "reviewer-demo");
    expect(screen.getByText("Decides cases the rules hand to a person")).toBeInTheDocument();
  });

  it("preselects the account named in the link", async () => {
    search = "persona=operator&next=%2Fops";
    show();
    expect(await screen.findByLabelText("Account")).toHaveValue("operator");
  });

  it("signs in as the account and goes to that role's home", async () => {
    server.use(
      recorded("post", "/auth/demo-persona", () =>
        HttpResponse.json({
          principal: { ...f.principal, role: "reviewer" },
          expires_at: f.ISO,
        }),
      ),
    );
    show();
    await userEvent.selectOptions(await screen.findByLabelText("Account"), "reviewer-demo");
    await userEvent.click(screen.getByRole("button", { name: "Sign in as Reviewer" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/review"));
    expect(callsTo("POST", "/auth/demo-persona")[0]?.body).toEqual({ handle: "reviewer-demo" });
    expect(callsTo("GET", "/auth/csrf")).toHaveLength(0);
  });

  it("shows a calm notice and no control when seeded accounts are off", async () => {
    server.use(
      http.get(`${TEST_BASE}/auth/demo-personas`, () =>
        HttpResponse.json({ error: "NOT_FOUND", message: "off" }, { status: 404 }),
      ),
    );
    show();
    expect(
      await screen.findByText("Seeded accounts are off on this deployment.", { exact: false }),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Account")).not.toBeInTheDocument();
  });

  it("offers a retry when the list fails", async () => {
    server.use(
      http.get(`${TEST_BASE}/auth/demo-personas`, () =>
        HttpResponse.json(
          { error: "INTERNAL", message: "boom", request_id: "r9" },
          { status: 500 },
        ),
      ),
    );
    show();
    expect(await screen.findByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("says so when the chosen account is refused", async () => {
    server.use(
      recorded("post", "/auth/demo-persona", () =>
        HttpResponse.json({ error: "NOT_FOUND", message: "no", request_id: "r" }, { status: 404 }),
      ),
    );
    show();
    await userEvent.click(await screen.findByRole("button", { name: /^Sign in as Persona/ }));
    expect(await screen.findByText(/not available here/)).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("shows a countdown when rate limited", async () => {
    server.use(
      recorded("post", "/auth/demo-persona", () =>
        HttpResponse.json(
          { error: "RATE_LIMITED", message: "slow", request_id: "r" },
          { status: 429, headers: { "Retry-After": "30" } },
        ),
      ),
    );
    show();
    await userEvent.click(await screen.findByRole("button", { name: /^Sign in as Persona/ }));
    expect(await screen.findByText(/Try again in 30s\./)).toBeInTheDocument();
  });
});

describe("persona helpers", () => {
  it("falls back to the role's line for unknown handles", () => {
    expect(personaBlurb({ handle: "merchant-hearth", role: "merchant" })).toMatch(
      /simulated carrier/,
    );
    expect(groupPersonas([]).length).toBe(0);
  });
});
