import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ActionBar } from "@/components/ui/action-bar";

describe("ActionBar", () => {
  it("sticks above the tab bar on phones and sits in flow from tablet up", () => {
    render(
      <ActionBar data-testid="bar">
        <button>Go</button>
      </ActionBar>,
    );
    const bar = screen.getByTestId("bar");
    expect(bar.className).toContain("fixed");
    expect(bar.className).toContain("md:static");
    expect(bar.className).toContain("env(safe-area-inset-bottom");
    expect(screen.getByRole("button", { name: "Go" })).toBeInTheDocument();
  });
});
