import * as React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
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

const signedOut = () =>
  server.use(
    http.get(`${TEST_BASE}/auth/me`, () =>
      HttpResponse.json({ error: "UNAUTHENTICATED", message: "x" }, { status: 401 }),
    ),
  );

beforeEach(() => {
  replace.mockClear();
  search = "";
});

describe("LoginPanels", () => {
  it("starts a demo session and goes to the buyer home", async () => {
    signedOut();
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Start demo session" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/home"));
    expect(callsTo("POST", "/auth/demo-session")).toHaveLength(1);
  });

  it("honours a safe next path", async () => {
    signedOut();
    search = "next=%2Forders%2Fabc";
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Start demo session" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/orders/abc"));
  });

  it("ignores an unsafe next path", async () => {
    signedOut();
    search = "next=https%3A%2F%2Fevil.test";
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Start demo session" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/home"));
  });

  it("signs staff in and uses the returned role's home", async () => {
    signedOut();
    server.use(
      recorded("post", "/auth/login", () =>
        HttpResponse.json({
          principal: { ...f.principal, role: "merchant", merchant_id: "mrc_northwind" },
          expires_at: f.ISO,
        }),
      ),
    );
    show();
    await userEvent.type(await screen.findByLabelText("Handle"), "northwind-ops");
    await userEvent.type(screen.getByLabelText("Password"), "secret");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/merchant"));
    expect(callsTo("POST", "/auth/login")[0]?.body).toEqual({
      handle: "northwind-ops",
      password: "secret",
    });
  });

  it("shows one message for a rejected staff login and does not leave the page", async () => {
    signedOut();
    server.use(
      recorded("post", "/auth/login", () =>
        HttpResponse.json(
          { error: "UNAUTHENTICATED", detail: "UNAUTHENTICATED", message: "no", request_id: "r" },
          { status: 401 },
        ),
      ),
    );
    show();
    await userEvent.type(await screen.findByLabelText("Handle"), "a");
    await userEvent.type(screen.getByLabelText("Password"), "b");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Handle or password was not accepted.")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Password")).toHaveAttribute("aria-invalid", "true");
  });

  it("explains a full demo and offers a retry", async () => {
    signedOut();
    server.use(
      recorded("post", "/auth/demo-session", () =>
        HttpResponse.json(
          { error: "UPSTREAM_UNAVAILABLE", message: "full", request_id: "r1" },
          { status: 503 },
        ),
      ),
    );
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Start demo session" }));
    expect(await screen.findByText("Service is unavailable")).toBeInTheDocument();
    expect(screen.getByText("Reference r1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("shows a countdown after a rate limit", async () => {
    signedOut();
    server.use(
      recorded("post", "/auth/demo-session", () =>
        HttpResponse.json(
          { error: "RATE_LIMITED", message: "slow", request_id: "r2" },
          { status: 429, headers: { "Retry-After": "30" } },
        ),
      ),
    );
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Start demo session" }));
    expect(await screen.findByText(/Try again in 30s\./)).toBeInTheDocument();
  });

  it("sends an already signed-in visitor straight to their home", async () => {
    show();
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/home"));
  });
});
