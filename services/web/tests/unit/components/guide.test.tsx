import { readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";

vi.mock("next-themes", () => ({ useTheme: () => ({ resolvedTheme: "dark", setTheme: vi.fn() }) }));

import { RunTheDemo } from "@/components/guide/run-the-demo";
import { PERSONA_TABLE, STEPS, personaHref } from "@/lib/guide/content";
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

/** Every route the app folder serves, with route groups dropped. */
function appRoutes(dir = join(process.cwd(), "app"), prefix = ""): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      const seg = name.startsWith("(") ? "" : `/${name}`;
      out.push(...appRoutes(full, prefix + seg));
    } else if (name === "page.tsx") {
      out.push(prefix || "/");
    }
  }
  return out;
}

describe("run the demo guide", () => {
  it("renders every section and every step", () => {
    render(<RunTheDemo />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Run the demo.");
    for (const h of [
      "What you are looking at",
      "Before you start",
      "The walkthrough",
      "Who is who",
      "Run it yourself",
      "Honest limits",
    ]) {
      expect(screen.getByRole("heading", { level: 2, name: h })).toBeInTheDocument();
    }
    expect(screen.getAllByRole("heading", { level: 3 })).toHaveLength(STEPS.length);
    expect(STEPS).toHaveLength(8);
  });

  it("names who acts in every step", () => {
    render(<RunTheDemo />);
    expect(screen.getAllByText(/^Notice ·/)).toHaveLength(STEPS.length);
  });

  it("links every step to a real route and a real sign-in path", () => {
    const routes = new Set(appRoutes());
    for (const s of STEPS) expect(routes.has(s.route), s.route).toBe(true);
    render(<RunTheDemo />);
    const hrefs = screen.getAllByRole("link").map((a) => a.getAttribute("href") ?? "");
    for (const h of hrefs) {
      if (!h.startsWith("/")) continue;
      expect(routes.has(h.split("?")[0] ?? ""), h).toBe(true);
    }
    expect(personaHref(STEPS[0]!)).toBe("/login?persona=buyer-alex&next=%2Fmandate%2Fnew");
  });

  it("lists the seeded accounts and the run commands", () => {
    render(<RunTheDemo />);
    const table = screen.getByRole("table");
    for (const p of PERSONA_TABLE) expect(within(table).getByText(p.handle)).toBeInTheDocument();
    expect(screen.getByText(/docker compose up/)).toBeInTheDocument();
    expect(screen.getByText(/pnpm install/)).toBeInTheDocument();
    expect(screen.getByText("PS_APIGATEWAY_DEMO_PERSONA_LOGIN=true")).toBeInTheDocument();
  });

  it("states the honest limits and carries no banned claims", () => {
    const { container } = render(<RunTheDemo />);
    const text = container.textContent ?? "";
    expect(text).toMatch(/merchant-funded, via PayPal's refund API/);
    expect(text).toMatch(/sandbox personal/i);
    expect(text).toMatch(/30 to 45 seconds/);
    expect(findBanned(text)).toEqual([]);
  });
});
