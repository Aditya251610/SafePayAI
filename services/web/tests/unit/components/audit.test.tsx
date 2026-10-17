import * as React from "react";
import { describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as f from "../../mocks/fixtures";
import { callsTo } from "../../mocks/handlers";
import { answer, renderApp } from "./helpers";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/audit",
}));
vi.mock("next-themes", () => ({ useTheme: () => ({ resolvedTheme: "dark", setTheme: vi.fn() }) }));
vi.mock("@/lib/api/config", () => ({ API_BASE_URL: "http://gateway.test/api" }));

import { AuditLog } from "@/components/audit/audit-log";
import { SessionProvider } from "@/lib/auth/session";
import { AnyRoleShell } from "@/components/shell/any-role-shell";

const row = (seq: number, over: Record<string, unknown> = {}) => ({
  ...f.auditRow,
  seq,
  summary: `Event ${seq}`,
  event_type: `type.${seq}`,
  ...over,
});

const page = (from: number, count: number, head = 60) => ({
  rows: Array.from({ length: count }, (_, i) => row(from - i)),
  lastRow: -1,
  head_seq: head,
});

describe("AuditLog", () => {
  it("shows the chain as intact with what was checked", async () => {
    renderApp(<AuditLog />);
    expect(await screen.findByText("Chain intact")).toBeInTheDocument();
    expect(screen.getByText(/Checked 12 entries up to #12 · sha256/)).toBeInTheDocument();
  });

  it("says plainly when the chain is broken and where", async () => {
    answer("get", "/audit/verify", 200, {
      ok: false,
      first_bad_seq: 7,
      reason: "hash mismatch",
      expected: "aaa",
      found: "bbb",
    });
    renderApp(<AuditLog />);
    expect(await screen.findByText("Chain broken")).toBeInTheDocument();
    expect(screen.getByText(/failed at entry #7 \(hash mismatch\)/)).toBeInTheDocument();
    expect(screen.getByText("expected aaa")).toBeInTheDocument();
    expect(screen.getByText("found bbb")).toBeInTheDocument();
  });

  it("lists entries with refs that link to the right screens", async () => {
    renderApp(<AuditLog />);
    const table = await screen.findByRole("table");
    expect(within(table).getByText("Order Captured")).toBeInTheDocument();
    expect(within(table).getByRole("link", { name: /order 444444/i })).toHaveAttribute(
      "href",
      `/orders/${f.IDS.order}`,
    );
    expect(within(table).getByRole("link", { name: /mandate 222222/i })).toHaveAttribute(
      "href",
      `/mandate/${f.IDS.mandate}`,
    );
  });

  it("pages older and newer with sequence cursors", async () => {
    answer("get", "/audit/entries", 200, page(60, 25));
    renderApp(<AuditLog />);
    await screen.findByText(/Showing 25 entries/);
    expect(screen.getByRole("button", { name: "Newer" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Older" }));
    await waitFor(() =>
      expect(callsTo("GET", "/audit/entries").some((c) => c.search.includes("before_seq=36"))).toBe(
        true,
      ),
    );
    await userEvent.click(await screen.findByRole("button", { name: "Newer" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Newer" })).toBeDisabled());
  });

  it("offers no older page on a short page", async () => {
    renderApp(<AuditLog />);
    await screen.findByRole("table");
    expect(screen.getByRole("button", { name: "Older" })).toBeDisabled();
  });

  it("filters by event type and can clear the filter", async () => {
    renderApp(<AuditLog />);
    await screen.findByRole("table");
    await userEvent.type(screen.getByLabelText("Event type"), "order.captured");
    await userEvent.click(screen.getByRole("button", { name: "Filter" }));
    await waitFor(() =>
      expect(
        callsTo("GET", "/audit/entries").some((c) =>
          c.search.includes("event_type=order.captured"),
        ),
      ).toBe(true),
    );
    await userEvent.click(await screen.findByRole("button", { name: "Clear" }));
    expect(screen.queryByRole("button", { name: "Clear" })).not.toBeInTheDocument();
  });

  it("has an empty state and an error state", async () => {
    answer("get", "/audit/entries", 200, { rows: [], lastRow: 0, head_seq: 0 });
    const { unmount } = renderApp(<AuditLog />);
    expect(await screen.findByText("No entries yet.")).toBeInTheDocument();
    unmount();
    answer("get", "/audit/entries", 500, { error: "internal_error", message: "x" });
    renderApp(<AuditLog />);
    expect(await screen.findAllByText("Something went wrong on our side")).not.toHaveLength(0);
  });

  it("states that model output is a draft, never a decision", async () => {
    renderApp(<AuditLog />);
    expect(
      await screen.findByText(/AI model output is logged as a draft, never as a decision/),
    ).toBeInTheDocument();
  });
});

describe("AnyRoleShell", () => {
  it("frames the page for whichever role is signed in", async () => {
    answer("get", "/auth/me", 200, { ...f.me, role: "reviewer", display_name: "demo-reviewer" });
    renderApp(
      <SessionProvider>
        <AnyRoleShell>
          <p>Audit page</p>
        </AnyRoleShell>
      </SessionProvider>,
    );
    expect(await screen.findByText("Audit page")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Review/ }).length).toBeGreaterThan(0);
  });
});
