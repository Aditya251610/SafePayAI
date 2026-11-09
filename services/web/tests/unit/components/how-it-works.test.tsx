import { beforeAll, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("next-themes", () => ({ useTheme: () => ({ resolvedTheme: "dark", setTheme: vi.fn() }) }));

import { HowItWorks } from "@/components/how/how-it-works";
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

describe("how it works", () => {
  it("shows all seven steps and the three actors", () => {
    render(<HowItWorks />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Where PayPal fits.");
    expect(screen.getAllByRole("heading", { level: 3 })).toHaveLength(7);
    for (const chip of ["PayPal does", "AI does", "Rules decide"]) {
      expect(screen.getAllByText(chip).length).toBeGreaterThanOrEqual(1);
    }
  });

  it("states the AI boundary", () => {
    render(<HowItWorks />);
    expect(
      screen.getByText("AI classifies and drafts. It never decides money."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("On any error or low confidence it hands the case to a person."),
    ).toBeInTheDocument();
  });

  it("labels the simulated carrier, sandbox and figures honestly", () => {
    render(<HowItWorks />);
    expect(screen.getByText("Simulated carrier")).toBeInTheDocument();
    expect(screen.getByText("PayPal sandbox order")).toBeInTheDocument();
    expect(screen.getByText(/Merchant-funded via PayPal refund/)).toBeInTheDocument();
    expect(screen.getAllByText("Illustration").length).toBeGreaterThanOrEqual(6);
  });

  it("makes no banned claims", () => {
    const { container } = render(<HowItWorks />);
    expect(findBanned(container.textContent ?? "")).toEqual([]);
  });
});
