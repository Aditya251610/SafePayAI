import { beforeAll, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("next-themes", () => ({ useTheme: () => ({ resolvedTheme: "dark", setTheme: vi.fn() }) }));

import { Story } from "@/components/landing/story";
import { ApiErrorNotice } from "@/components/shared/api-error";
import { ApiError } from "@/lib/api/errors";
import { findBanned } from "@/lib/honesty/banned";

beforeAll(() => {
  window.matchMedia = ((query: string) => ({
    matches: query.includes("reduce"),
    media: query,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    addListener: () => undefined,
    removeListener: () => undefined,
    onchange: null,
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
});

describe("landing story", () => {
  it("has all four scenes and the closing call to action at rest", () => {
    render(<Story />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Set the cap.");
    for (const n of ["01 · Mandate", "02 · Shop", "03 · Protect", "04 · Refund"]) {
      expect(screen.getByText(n)).toBeInTheDocument();
    }
    expect(screen.getAllByRole("link", { name: "Sign your first mandate" })).toHaveLength(2);
  });

  it("labels every example figure as an illustration", () => {
    render(<Story />);
    expect(screen.getAllByText("Illustration").length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText(/Carrier status is simulated/)).toBeInTheDocument();
    expect(screen.getByText("Merchant-funded via PayPal.")).toBeInTheDocument();
  });

  it("shows final values without animation under reduced motion", () => {
    render(<Story />);
    expect(screen.getByText("+6")).toBeInTheDocument();
    expect(screen.getByText("+$48.20")).toBeInTheDocument();
  });

  it("makes no banned claims", () => {
    const { container } = render(<Story />);
    expect(findBanned(container.textContent ?? "")).toEqual([]);
  });
});

describe("ApiErrorNotice", () => {
  it("lists field problems and omits retry for non-retryable codes", () => {
    const err = new ApiError({
      code: "VALIDATION_ERROR",
      message: "x",
      status: 422,
      fields: [{ field: "terms.currency", message: "Field required" }],
    });
    render(<ApiErrorNotice error={err} onRetry={() => undefined} />);
    expect(screen.getByText("terms.currency: Field required")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });
  it("treats a non-ApiError as a network failure", () => {
    render(<ApiErrorNotice error={new Error("boom")} onRetry={() => undefined} />);
    expect(screen.getByText("No connection")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
