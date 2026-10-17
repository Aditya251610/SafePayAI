import * as React from "react";
import { describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { server } from "../../mocks/server";
import { callsTo, recorded } from "../../mocks/handlers";
import * as f from "../../mocks/fixtures";
import { answer, renderApp } from "./helpers";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/ops",
}));
vi.mock("@/lib/api/config", () => ({ API_BASE_URL: "http://gateway.test/api" }));

import { OpsConsole, effectivelyFrozen } from "@/components/ops/ops-console";
import { ReviewQueue, formatAge } from "@/components/review/review-queue";

const status = (over: Record<string, unknown> = {}) =>
  answer("get", "/ops/status", 200, {
    demo_mode: true,
    money_routes_enabled: true,
    refunds_frozen: "true",
    build_id: "b1",
    ...over,
  });

describe("effectivelyFrozen", () => {
  it("treats unknown as frozen", () => {
    expect(effectivelyFrozen("true")).toBe(true);
    expect(effectivelyFrozen("unknown")).toBe(true);
    expect(effectivelyFrozen("false")).toBe(false);
  });
});

describe("OpsConsole", () => {
  it("shows the switches and the case list", async () => {
    renderApp(<OpsConsole />);
    expect(await screen.findByText("Money routes on")).toBeInTheDocument();
    expect(screen.getByText("Demo mode on")).toBeInTheDocument();
    expect(screen.getByText("Refunds are paused.")).toBeInTheDocument();
    expect(await screen.findByText("Late")).toBeInTheDocument();
    expect(screen.getByText(/There is no button here/)).toBeInTheDocument();
  });

  it("calls an unknown flag frozen", async () => {
    status({ refunds_frozen: "unknown" });
    renderApp(<OpsConsole />);
    expect(await screen.findByText("Unknown · treated as frozen")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Unfreeze refunds" })).toBeInTheDocument();
  });

  it("needs a reason before it will even ask to confirm", async () => {
    renderApp(<OpsConsole />);
    await userEvent.click(await screen.findByRole("button", { name: "Unfreeze refunds" }));
    expect(
      await screen.findByText("Say why. The reason is written to the audit log."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(callsTo("POST", "/ops/freeze")).toHaveLength(0);
  });

  it("unfreezes after an in-page confirmation, with the ops_freeze token and the reason", async () => {
    renderApp(<OpsConsole />);
    await userEvent.type(await screen.findByLabelText("Reason"), "Demo reset");
    await userEvent.click(screen.getByRole("button", { name: "Unfreeze refunds" }));
    const dialog = await screen.findByRole("dialog");
    expect(callsTo("POST", "/ops/freeze")).toHaveLength(0);
    await userEvent.click(within(dialog).getByRole("button", { name: "Yes, unfreeze" }));
    expect(await screen.findByText(/Refunds are unfrozen/)).toBeInTheDocument();
    expect(callsTo("POST", "/ops/freeze")[0]?.body).toEqual({
      frozen: false,
      reason: "Demo reset",
    });
    expect(callsTo("GET", "/auth/csrf")[0]?.search).toBe("?purpose=ops_freeze");
  });

  it("freezes a running system", async () => {
    status({ refunds_frozen: "false" });
    renderApp(<OpsConsole />);
    await userEvent.type(await screen.findByLabelText("Reason"), "Investigating");
    await userEvent.click(screen.getByRole("button", { name: "Freeze refunds" }));
    await userEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Yes, freeze" }),
    );
    expect(await screen.findByText("Refunds are frozen.")).toBeInTheDocument();
    expect(callsTo("POST", "/ops/freeze")[0]?.body).toEqual({
      frozen: true,
      reason: "Investigating",
    });
  });

  it("re-reads the status after a timeout instead of assuming", async () => {
    server.use(
      recorded("post", "/ops/freeze", () =>
        HttpResponse.json({ error: "UPSTREAM_TIMEOUT", message: "t" }, { status: 504 }),
      ),
    );
    renderApp(<OpsConsole />);
    await userEvent.type(await screen.findByLabelText("Reason"), "x");
    await userEvent.click(screen.getByRole("button", { name: "Unfreeze refunds" }));
    await userEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Yes, unfreeze" }),
    );
    expect(await screen.findByText(/Checking what happened/)).toBeInTheDocument();
    expect(callsTo("POST", "/ops/freeze")).toHaveLength(1);
  });

  it("shows a refused change", async () => {
    answer("post", "/ops/freeze", 503, { error: "MONEY_ROUTES_DISABLED", message: "off" });
    renderApp(<OpsConsole />);
    await userEvent.type(await screen.findByLabelText("Reason"), "x");
    await userEvent.click(screen.getByRole("button", { name: "Unfreeze refunds" }));
    await userEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Yes, unfreeze" }),
    );
    expect(await screen.findByText("Money actions are switched off")).toBeInTheDocument();
  });

  it("advances the demo clock and can reset it", async () => {
    renderApp(<OpsConsole />);
    await userEvent.click(await screen.findByRole("button", { name: "+1 day" }));
    await userEvent.click(screen.getByRole("button", { name: "+7 days" }));
    await userEvent.click(screen.getByRole("button", { name: "Reset" }));
    const calls = callsTo("POST", "/tracking/demo/clock/advance").map(
      (c) => (c.body as { delta_seconds: number }).delta_seconds,
    );
    expect(calls).toEqual([86400, 604800]);
    expect(callsTo("POST", "/tracking/demo/clock/reset")).toHaveLength(1);
    expect(
      callsTo("POST", "/tracking/demo/clock/advance")[0]?.headers["idempotency-key"],
    ).toBeTruthy();
  });

  it("does not render the demo clock when demo mode is off", async () => {
    status({ demo_mode: false });
    renderApp(<OpsConsole />);
    await screen.findByText("Demo mode off");
    expect(screen.queryByText(/Demo clock/)).not.toBeInTheDocument();
    expect(callsTo("GET", "/tracking/demo/clock")).toHaveLength(0);
  });

  it("removes the demo clock if the gateway answers 404", async () => {
    answer("get", "/tracking/demo/clock", 404, { error: "NOT_FOUND", message: "x" });
    renderApp(<OpsConsole />);
    await screen.findByText("Demo mode on");
    await vi.waitFor(() => expect(screen.queryByText(/Demo clock/)).not.toBeInTheDocument());
  });

  it("fails clearly when the status cannot load", async () => {
    answer("get", "/ops/status", 500, { error: "internal_error", message: "x" });
    renderApp(<OpsConsole />);
    expect(await screen.findByText("Something went wrong on our side")).toBeInTheDocument();
  });
});

describe("ReviewQueue", () => {
  it("lists waiting cases and says it is read-only", async () => {
    renderApp(<ReviewQueue />);
    expect(await screen.findByText("Read-only in this build")).toBeInTheDocument();
    expect(await screen.findByText("POLICY_CAP")).toBeInTheDocument();
    expect(screen.getByText("Over the policy cap.")).toBeInTheDocument();
    expect(screen.getByText("1 min")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
  it("has an empty and an error state", async () => {
    answer("get", "/resolution/review/queue", 200, { items: [] });
    const { unmount } = renderApp(<ReviewQueue />);
    expect(await screen.findByText("The queue is empty.")).toBeInTheDocument();
    unmount();
    answer("get", "/resolution/review/queue", 403, { error: "FORBIDDEN", message: "x" });
    renderApp(<ReviewQueue />);
    expect(await screen.findByText("Not available for this account")).toBeInTheDocument();
  });
  it("formats ages", () => {
    expect(formatAge(30)).toBe("0 min");
    expect(formatAge(3 * 3600 + 12 * 60)).toBe("3 h 12 min");
    expect(formatAge(3 * 86400)).toBe("3 d");
    expect(formatAge(-1)).toBe("—");
  });
  it("keeps fixtures honest", () => {
    expect(f.IDS.case).toBeTruthy();
  });
});
