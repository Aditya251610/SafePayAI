import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SandboxBanner } from "@/components/shared/sandbox-banner";

// The sandbox notice is persistent and has no dismiss control.

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
