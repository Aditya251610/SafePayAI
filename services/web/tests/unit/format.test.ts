import { describe, expect, it } from "vitest";
import { formatMoney } from "@/lib/format/money";
import { formatDate, formatDateTime } from "@/lib/format/date";

describe("formatMoney", () => {
  it("formats minor units for display", () => {
    expect(formatMoney(4820)).toBe("$48.20");
    expect(formatMoney(50000)).toBe("$500.00");
    expect(formatMoney(5)).toBe("$0.05");
    expect(formatMoney(0)).toBe("$0.00");
    expect(formatMoney(123456789)).toBe("$1,234,567.89");
  });
  it("handles negatives", () => {
    expect(formatMoney(-4820)).toBe("-$48.20");
  });
  it("refuses non-integer input", () => {
    expect(formatMoney(1.5)).toBe("—");
    expect(formatMoney(Number.NaN)).toBe("—");
  });
  it("respects zero-decimal currencies", () => {
    expect(formatMoney(500, "JPY")).toMatch(/500$/);
  });
});

describe("dates", () => {
  it("formats ISO strings and tolerates garbage", () => {
    expect(formatDate("2026-10-17T12:00:00Z", "en-US", "UTC")).toBe("Oct 17, 2026");
    expect(formatDateTime("2026-10-17T12:00:00Z", "en-US", "UTC")).toContain("Oct 17, 2026");
    expect(formatDate("not a date")).toBe("—");
  });
});
