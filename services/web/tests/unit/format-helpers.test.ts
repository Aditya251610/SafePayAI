import { describe, expect, it } from "vitest";
import { CASE_STATES } from "@/lib/api/schemas/common";
import { CASE_RAIL_STEPS, railStep } from "@/lib/format/case-rail";
import { METER_CELLS, meterCells } from "@/lib/format/meter";
import { NAV, isActive } from "@/lib/auth/nav";

describe("meterCells", () => {
  it("maps a ratio to filled cells", () => {
    expect(meterCells(0, 100)).toBe(0);
    expect(meterCells(50, 100)).toBe(10);
    expect(meterCells(100, 100)).toBe(METER_CELLS);
    expect(meterCells(150, 100)).toBe(METER_CELLS);
  });
  it("shows at least one cell for any positive spend", () => {
    expect(meterCells(1, 1000)).toBe(1);
  });
  it("is safe on bad input", () => {
    expect(meterCells(5, 0)).toBe(0);
    expect(meterCells(Number.NaN, 10)).toBe(0);
    expect(meterCells(-3, 10)).toBe(0);
  });
});

describe("railStep", () => {
  it("places every backend state on the rail", () => {
    for (const s of CASE_STATES) {
      const i = railStep(s);
      expect(i).toBeGreaterThanOrEqual(0);
      expect(i).toBeLessThan(CASE_RAIL_STEPS.length);
    }
  });
  it("orders the lifecycle", () => {
    expect(railStep("MONITORING")).toBe(0);
    expect(railStep("OFFERED")).toBe(2);
    expect(railStep("REFUNDING")).toBe(3);
    expect(railStep("RESOLVED_REFUNDED")).toBe(4);
  });
  it("puts unknown states at the start", () => {
    expect(railStep("SOMETHING_NEW")).toBe(0);
  });
});

describe("nav", () => {
  it("gives buyers four tabs", () => {
    expect(NAV.buyer).toHaveLength(4);
  });
  it("matches nested paths as active", () => {
    expect(isActive("/orders/abc", "/orders")).toBe(true);
    expect(isActive("/orders", "/orders")).toBe(true);
    expect(isActive("/ordersx", "/orders")).toBe(false);
  });
});
