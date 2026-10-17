import { afterEach, describe, expect, it } from "vitest";
import {
  approveHosts,
  canRedirectToPayPal,
  isFinalStatus,
  outcomeFor,
} from "@/lib/checkout/outcome";
import { checkLabel, reasonLabel } from "@/lib/format/checks";
import { ORDER_STATUSES } from "@/lib/api/schemas/checkout";
import { findBanned } from "@/lib/honesty/banned";

describe("outcomeFor", () => {
  it("has a message for every order status", () => {
    for (const s of ORDER_STATUSES) {
      const o = outcomeFor(s);
      expect(o.title.length, s).toBeGreaterThan(5);
      expect(findBanned(`${o.title} ${o.text}`), s).toEqual([]);
    }
  });
  it("only calls a payment captured when the order says so", () => {
    expect(outcomeFor("CAPTURED").tone).toBe("ok");
    for (const s of ["CAPTURE_PENDING", "CAPTURE_UNKNOWN", "CAPTURE_FAILED", "AWAITING_APPROVAL"]) {
      expect(outcomeFor(s).tone).not.toBe("ok");
      expect(outcomeFor(s).title).not.toMatch(/captured/i);
    }
  });
  it("never says nothing was charged when the outcome is unknown or failed", () => {
    for (const s of ["CAPTURE_UNKNOWN", "CAPTURE_FAILED", "CAPTURE_PENDING"]) {
      expect(`${outcomeFor(s).title} ${outcomeFor(s).text}`).not.toMatch(/nothing was charged/i);
    }
  });
  it("tells the buyer not to pay twice when unsure", () => {
    expect(outcomeFor("CAPTURE_UNKNOWN").text).toMatch(/Do not pay again/);
  });
  it("falls back for an unknown status", () => {
    expect(outcomeFor("SOMETHING_NEW").action).toBe("orders");
  });
  it("knows which statuses are final", () => {
    expect(isFinalStatus("CAPTURED")).toBe(true);
    expect(isFinalStatus("CAPTURE_PENDING")).toBe(false);
  });
});

describe("PayPal redirect guard", () => {
  afterEach(() => {
    delete process.env.NEXT_PUBLIC_PS_WEB_PAYPAL_APPROVE_HOST_ALLOWLIST;
  });
  it("allows only the sandbox host by default", () => {
    expect(approveHosts()).toEqual(["www.sandbox.paypal.com"]);
    expect(canRedirectToPayPal("https://www.sandbox.paypal.com/checkoutnow?token=1")).toBe(true);
    expect(canRedirectToPayPal("https://www.paypal.com/checkoutnow?token=1")).toBe(false);
    expect(canRedirectToPayPal("https://evil.test/www.sandbox.paypal.com")).toBe(false);
    expect(canRedirectToPayPal("http://www.sandbox.paypal.com/x")).toBe(false);
  });
  it("reads a comma separated allowlist", () => {
    process.env.NEXT_PUBLIC_PS_WEB_PAYPAL_APPROVE_HOST_ALLOWLIST = "a.test, b.test";
    expect(approveHosts()).toEqual(["a.test", "b.test"]);
    expect(canRedirectToPayPal("https://b.test/x")).toBe(true);
  });
});

describe("check labels", () => {
  it("names checks and reasons in plain words", () => {
    expect(checkLabel("mandate_evaluate")).toBe("Mandate rules");
    expect(checkLabel("some_new_check")).toBe("some new check");
    expect(reasonLabel("OVER_CAP")).toBe("Over the cap");
    expect(reasonLabel("NEW_CODE")).toBe("NEW_CODE");
    expect(reasonLabel(null)).toBeNull();
  });
});
