import { describe, expect, it } from "vitest";
import { parseMoneyInput } from "@/lib/format/money-input";
import {
  caseKindLabel,
  caseStateLabel,
  mandateStatusLabel,
  merchantLabel,
  orderStatusLabel,
  shortId,
} from "@/lib/format/label";
import {
  buildTerms,
  defaultFormState,
  toLocalInput,
  toServerTimestamp,
  type MandateFormState,
} from "@/lib/mandate/build-terms";

describe("parseMoneyInput", () => {
  it.each([
    ["500", 50000],
    ["500.5", 50050],
    ["500.55", 50055],
    ["$1,250.00", 125000],
    ["0.07", 7],
    [" 12 ", 1200],
    ["10.", 1000],
  ])("reads %s as %i minor units", (text, expected) => {
    expect(parseMoneyInput(text)).toBe(expected);
  });
  it.each(["", "abc", "-5", "1.234", "1e5", "12,34,56x", "1.2.3"])("rejects %j", (text) => {
    expect(parseMoneyInput(text)).toBeNull();
  });
  it("is exact where floats are not", () => {
    expect(parseMoneyInput("0.29")).toBe(29);
    expect(parseMoneyInput("1.15")).toBe(115);
  });
});

describe("labels", () => {
  it("shortens ids and prettifies merchant ids", () => {
    expect(shortId("0f1e2d3c-aaaa-4bbb-8ccc-111122223333", 6)).toBe("0F1E2D");
    expect(merchantLabel("mrc_northwind")).toBe("Northwind");
    expect(merchantLabel("mrc_atlas-cables")).toBe("Atlas Cables");
  });
  it("labels states and falls back to the raw value", () => {
    expect(caseStateLabel("OFFERED")).toBe("Offer ready");
    expect(caseStateLabel("NEW")).toBe("NEW");
    expect(caseKindLabel("LATE")).toBe("Late");
    expect(orderStatusLabel("CAPTURED")).toBe("Captured");
    expect(mandateStatusLabel("active")).toBe("Mandate active");
  });
});

describe("buildTerms", () => {
  const base = (over: Partial<MandateFormState> = {}): MandateFormState => ({
    ...defaultFormState(new Date("2026-10-17T12:00:00")),
    merchants: ["mrc_northwind", "mrc_atlas"],
    intent: "Headphones under $150",
    ...over,
  });

  it("builds the request body in integer minor units", () => {
    const r = buildTerms(base({ perLine: "3" }));
    expect(r.errors).toBeNull();
    expect(r.terms).toMatchObject({
      currency: "USD",
      max_total_minor: 50000,
      max_qty_per_line: 3,
      intent_text: "Headphones under $150",
      protection: { kinds_covered: ["LATE", "LOST"], max_refund_minor: 15000, deliver_by_days: 7 },
    });
    expect(r.terms?.merchant_allowlist).toEqual([
      { merchant_id: "mrc_northwind", display_name: "Northwind" },
      { merchant_id: "mrc_atlas", display_name: "Atlas" },
    ]);
    expect(r.terms?.expires_at).toMatch(/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/);
  });

  it("omits max_qty_per_line when empty", () => {
    const r = buildTerms(base({ perLine: "" }));
    expect(r.terms && "max_qty_per_line" in r.terms).toBe(false);
  });

  it("covers a single kind when only one is ticked", () => {
    expect(buildTerms(base({ lost: false })).terms?.protection.kinds_covered).toEqual(["LATE"]);
  });

  it("reports every problem at once", () => {
    const r = buildTerms(
      base({
        cap: "0",
        maxRefund: "x",
        perLine: "1.5",
        deliverDays: "45",
        ends: "",
        merchants: [],
        intent: "  ",
        late: false,
        lost: false,
      }),
    );
    expect(r.terms).toBeNull();
    expect(Object.keys(r.errors ?? {}).sort()).toEqual(
      ["cap", "deliverDays", "ends", "intent", "late", "maxRefund", "merchants", "perLine"].sort(),
    );
  });

  it("limits the allowlist to five shops and the intent to 500 characters", () => {
    const six = ["a", "b", "c", "d", "e", "f"].map((s) => `mrc_${s}`);
    expect(buildTerms(base({ merchants: six })).errors?.merchants).toMatch(/at most five/);
    expect(buildTerms(base({ intent: "x".repeat(501) })).errors?.intent).toMatch(/500/);
  });

  it("formats dates for the server and the date input", () => {
    expect(toServerTimestamp("2026-10-30T12:00")).toMatch(/Z$/);
    expect(toServerTimestamp("nope")).toBeNull();
    expect(toLocalInput(new Date(2026, 9, 5, 7, 3))).toBe("2026-10-05T07:03");
  });
});
