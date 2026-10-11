import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SandboxBanner } from "@/components/shared/sandbox-banner";

// Smoke test standing in for test-plan.md's label-matrix/crawl test
// (REQ-WB-002: persistent, non-dismissible SANDBOX banner on every page).
// Wave 5 should extend this into the full honesty-label crawl across routes.

describe("SandboxBanner", () => {
  it("renders the exact required sandbox disclosure text", () => {
    render(<SandboxBanner />);
    expect(
      screen.getByText(/Sandbox only\. No real money\. Seeded catalog\. Simulated carrier\./i),
    ).toBeInTheDocument();
  });

  it("does not render a dismiss/close control", () => {
    render(<SandboxBanner />);
    expect(screen.queryByRole("button", { name: /close|dismiss/i })).not.toBeInTheDocument();
  });
});
