import * as React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../mocks/server";
import { TEST_BASE } from "../../mocks/handlers";
import { makeQueryClient } from "@/lib/query/provider";

const replace = vi.fn();
let pathname = "/home";
vi.mock("next/navigation", () => ({
  usePathname: () => pathname,
  useRouter: () => ({ replace, push: vi.fn() }),
}));
vi.mock("next-themes", () => ({
  useTheme: () => ({ resolvedTheme: "dark", setTheme: vi.fn() }),
}));
vi.mock("@/lib/api/config", () => ({ API_BASE_URL: "http://gateway.test/api" }));

import { SessionProvider, useSession } from "@/lib/auth/session";
import { RequireRole } from "@/components/shared/require-role";
import { AppShell } from "@/components/shell/app-shell";
import { ThemeToggle } from "@/components/shared/theme-toggle";
import { SandboxBanner } from "@/components/shared/sandbox-banner";
import { FooterDisclosure } from "@/components/shared/footer-disclosure";
import { WakingUp } from "@/components/shared/waking-up";

function wrap(ui: React.ReactNode) {
  const qc = makeQueryClient();
  qc.setDefaultOptions({ queries: { retry: false } });
  return render(
    <QueryClientProvider client={qc}>
      <SessionProvider>{ui}</SessionProvider>
    </QueryClientProvider>,
  );
}

const meAs = (role: string) =>
  http.get(`${TEST_BASE}/auth/me`, () =>
    HttpResponse.json({
      actor_type: role,
      actor_id: "a",
      role,
      auth_method: "session",
      display_name: `demo-${role}`,
      merchant_id: null,
      session_expires_at: null,
    }),
  );

beforeEach(() => {
  replace.mockClear();
  pathname = "/home";
});

describe("disclosures", () => {
  it("banner has no dismiss control and footer disclaims PayPal", () => {
    render(
      <>
        <SandboxBanner />
        <FooterDisclosure />
      </>,
    );
    expect(
      screen.getByText(/Sandbox only\. No real money\. Seeded catalog\. Simulated carrier\./),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText(/Not affiliated with or endorsed by PayPal\./)).toBeInTheDocument();
  });
  it("waking state is announced", () => {
    render(<WakingUp />);
    expect(screen.getByRole("status")).toHaveTextContent(/Waking up/);
  });
});

describe("ThemeToggle", () => {
  it("offers the opposite mode", async () => {
    render(<ThemeToggle />);
    expect(await screen.findByRole("button", { name: "Switch to light mode" })).toBeInTheDocument();
  });
});

describe("SessionProvider and RequireRole", () => {
  it("shows a skeleton while loading, then the page for the right role", async () => {
    server.use(meAs("buyer"));
    const { container } = wrap(
      <RequireRole roles={["buyer"]}>
        <p>Buyer page</p>
      </RequireRole>,
    );
    expect(container.querySelector("[aria-busy=true]")).not.toBeNull();
    expect(await screen.findByText("Buyer page")).toBeInTheDocument();
  });

  it("sends an anonymous visitor to login with the return path", async () => {
    server.use(
      http.get(`${TEST_BASE}/auth/me`, () =>
        HttpResponse.json({ error: "UNAUTHENTICATED", message: "x" }, { status: 401 }),
      ),
    );
    pathname = "/orders/abc";
    wrap(
      <RequireRole roles={["buyer"]}>
        <p>Buyer page</p>
      </RequireRole>,
    );
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login?next=%2Forders%2Fabc"));
    expect(screen.queryByText("Buyer page")).not.toBeInTheDocument();
  });

  it("shows a role mismatch screen with a link to the right home", async () => {
    server.use(meAs("merchant"));
    wrap(
      <RequireRole roles={["buyer"]}>
        <p>Buyer page</p>
      </RequireRole>,
    );
    expect(await screen.findByText("Wrong account type")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to your home" })).toHaveAttribute(
      "href",
      "/merchant",
    );
    expect(screen.queryByText("Buyer page")).not.toBeInTheDocument();
  });

  it("lets any signed-in role through an 'any' gate", async () => {
    server.use(meAs("reviewer"));
    wrap(
      <RequireRole roles="any">
        <p>Audit</p>
      </RequireRole>,
    );
    expect(await screen.findByText("Audit")).toBeInTheDocument();
  });

  it("offers a retry when the session cannot be loaded", async () => {
    server.use(
      http.get(`${TEST_BASE}/auth/me`, () =>
        HttpResponse.json({ error: "internal_error", message: "boom" }, { status: 500 }),
      ),
    );
    wrap(
      <RequireRole roles={["buyer"]}>
        <p>Buyer page</p>
      </RequireRole>,
    );
    expect(await screen.findByText("Could not load your session")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("signs out through the gateway and returns to anonymous", async () => {
    server.use(meAs("buyer"));
    function Probe() {
      const { session, signOut } = useSession();
      return (
        <>
          <p>status:{session.status}</p>
          <button onClick={() => void signOut()}>out</button>
        </>
      );
    }
    wrap(<Probe />);
    expect(await screen.findByText("status:authenticated")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "out" }));
    expect(await screen.findByText("status:anonymous")).toBeInTheDocument();
  });
});

describe("AppShell", () => {
  it("renders navigation for the role and marks the current page", async () => {
    server.use(meAs("buyer"));
    pathname = "/orders/abc";
    wrap(
      <AppShell role="buyer">
        <p>Content</p>
      </AppShell>,
    );
    expect(screen.getByText("Content")).toBeInTheDocument();
    const orders = screen.getAllByRole("link", { name: /Orders/ });
    expect(orders.length).toBeGreaterThanOrEqual(1);
    expect(orders.every((l) => l.getAttribute("aria-current") === "page")).toBe(true);
    expect(screen.getAllByRole("navigation", { name: "Main" })).toHaveLength(3);
    expect(await screen.findAllByText("demo-buyer")).not.toHaveLength(0);
  });

  it("gives staff their own navigation", () => {
    server.use(meAs("operator"));
    pathname = "/ops";
    wrap(
      <AppShell role="operator">
        <p>Content</p>
      </AppShell>,
    );
    expect(screen.getAllByRole("link", { name: /Controls|Ops/ }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("link", { name: "Shop" })).not.toBeInTheDocument();
  });
});
